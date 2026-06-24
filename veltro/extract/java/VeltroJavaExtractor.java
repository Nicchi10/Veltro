/*
 *
 * veltro/extract/java/VeltroJavaExtractor.java
 *
 * Extractor: Java source -> Veltro '.vel' text, using the JDK's own Compiler
 * Tree API (com.sun.source / javax.tools). This is the Java twin of
 * veltro/extract/python_ast.py: where the Python extractor uses Python's
 * authoritative 'ast' module, this one uses Java's authoritative parser
 * (javac), so the failure mode is omission, never invention.
 *
 * Why a standalone Java program and not a Python regex: a regex sees only text
 * and cannot tell 'extends' from 'implements', cannot resolve generics, and
 * cannot see annotations. javac knows all of this for sure. We work at the
 * PARSE level only (task.parse(), no attribution), so NO classpath and NO
 * compilation of the target project is required: it runs on any .java folder.
 *
 * What it captures:
 *     - one module per Java package (the dotted package name)
 *     - classes, interfaces, enums, @interface (annotation -> interface)
 *     - 'abstract class' -> 'class abstract'
 *     - fields (Type name [= initializer]) with visibility + static
 *     - methods and constructors, with typed parameters and return types
 *     - 'extends'  -> 'extend' edges; 'implements' -> 'impl' edges
 *       (interfaces' super-interfaces are 'extend' too); associations are left
 *       for the Veltro parser to derive from field types
 *
 * What it skips (v0, on purpose, mirroring the Python extractor):
 *     - nested / inner type declarations (only top-level types are emitted)
 *     - annotations themselves (kept out of the model for now)
 *     - a class's javadoc (no '>' doc lines yet)
 *     - generic type parameters of methods (<T> ... ) and throws clauses
 *     - static/instance initializer blocks
 *
 * Pick the JDK version: javac can only parse source up to its OWN language
 * level, so use a JDK at least as new as the target project (e.g. Spring uses
 * Java 17 syntax -- run this with JDK 17+, not JDK 8, or javac error-recovers
 * into a corrupt .vel).
 *
 * How to run it:
 *
 *   On JDK 9+ the supported Compiler Tree API (com.sun.source.*) is on the
 *   classpath, but this extractor also reads two INTERNAL javac packages (for
 *   the authoritative enum-constant flag, see isEnumConstant), which the module
 *   system encapsulates -- so both javac and java need --add-exports:
 *
 *     EXPORTS="--add-exports jdk.compiler/com.sun.tools.javac.tree=ALL-UNNAMED \
 *              --add-exports jdk.compiler/com.sun.tools.javac.code=ALL-UNNAMED"
 *
 *     1. Compile once (writes VeltroJavaExtractor.class next to the source):
 *         javac $EXPORTS veltro/extract/java/VeltroJavaExtractor.java
 *
 *     2. Extract a source folder to a .vel file (or omit --out for stdout):
 *         java $EXPORTS -cp veltro/extract/java VeltroJavaExtractor <src_dir> --out out.vel
 *
 *   On JDK 8 there is no module system (no --add-exports), but the same classes
 *   live in <JDK>/lib/tools.jar, which is NOT on the default classpath, so add
 *   it instead -- note JDK 8 only parses sources up to Java 8:
 *
 *         javac -cp "$JAVA_HOME/lib/tools.jar" veltro/extract/java/VeltroJavaExtractor.java
 *         java  -cp "veltro/extract/java:$JAVA_HOME/lib/tools.jar" VeltroJavaExtractor <src_dir> --out out.vel
 *
 *   On a real project, clone it first then point at its source root, e.g.
 *   './spring/src/main/java'. The emitted .vel is validated and turned into the
 *   JSON model by the existing Python tooling:  python -m veltro out.vel
 */

import com.sun.source.tree.ClassTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.ExpressionTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.JavacTask;

import com.sun.tools.javac.code.Flags;
import com.sun.tools.javac.tree.JCTree;

import javax.lang.model.element.Modifier;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

import java.io.File;
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class VeltroJavaExtractor {

    // Bases that carry no domain meaning, so they never become an edge.
    private static final Set<String> IGNORED_BASES = new HashSet<String>(
            Arrays.asList("Object", "Enum", "Annotation", "Record"));

    // Veltro line-start keywords. A public member whose name is one of these
    // would collide with a declaration (a field 'module str' would read as a
    // 'module' line), so such a member must keep an explicit '+'. Methods are
    // safe (the '(' tells them apart), but forcing '+' on them too is harmless.
    private static final Set<String> RESERVED_NAMES = new HashSet<String>(
            Arrays.asList("veltro", "module", "class", "interface", "enum", "rel"));

    // ============ A SINGLE INHERITANCE EDGE ============

    /**
     * One written relation: from -> kind -> to (kind is 'extend' or 'impl').
     */
    private static final class Edge {
        final String from;
        final String kind;
        final String to;

        Edge(String from, String kind, String to) {
            this.from = from;
            this.kind = kind;
            this.to = to;
        }
    }

    // ============ NAME / TYPE HELPERS ============

    /**
     * The simple (last) name of a type expression used as a base or a field
     * type, with any generic arguments and any package qualifier removed.
     *
     * @param typeTree a type expression, e.g. 'java.util.List<String>'
     * @return the simple name, e.g. 'List', or "" if it cannot be determined
     */
    private static String simpleName(Tree typeTree) {
        if (typeTree == null) {
            return "";
        }
        String text = typeTree.toString().trim();

        // Drop generic arguments: 'List<String>' -> 'List'
        int angle = text.indexOf('<');
        if (angle >= 0) {
            text = text.substring(0, angle);
        }
        // Drop array brackets: 'String[]' -> 'String'
        int bracket = text.indexOf('[');
        if (bracket >= 0) {
            text = text.substring(0, bracket);
        }
        // Drop the package qualifier: 'com.acme.Bar' -> 'Bar'
        int dot = text.lastIndexOf('.');
        if (dot >= 0) {
            text = text.substring(dot + 1);
        }
        return text.trim();
    }

    /**
     * Translate a Java type expression into the Veltro type syntax.
     *
     * Java already writes generics with '<>', so the main job is to drop the
     * spaces javac prints around '< > ,' (Veltro keeps generic commas tight)
     * and to flatten wildcards, which would otherwise smuggle a space (and a
     * stray 'extends'/'super' identifier) into the type:
     *     '? extends Number' -> 'Number'
     *     '? super Number'   -> 'Number'
     *     '?'                -> 'Object'
     * Varargs '...' become an array '[]'.
     *
     * @param typeTree a type expression node, or null for a void return
     * @return the Veltro type, e.g. 'Map<String,Object>', or 'void' if null
     */
    private static String javaTypeToVeltro(Tree typeTree) {
        if (typeTree == null) {
            return "void";
        }
        String text = typeTree.toString();

        // Flatten wildcards to their bound (or Object for an unbounded one).
        text = text.replace("? extends ", "");
        text = text.replace("? super ", "");
        text = text.replace("?", "Object");

        // Varargs -> array.
        text = text.replace("...", "[]");

        // Collapse the spacing javac leaves around generic punctuation.
        text = text.replaceAll("\\s*([<>,])\\s*", "$1");
        return text.trim();
    }

    /**
     * The visibility marker for a member from its modifier flags.
     *
     * Java's default (no modifier) access is package-private, which maps onto
     * Veltro's '@'. Members declared inside an interface are implicitly public.
     *
     * @param flags         the member's modifier set
     * @param insideInterface true when the member belongs to an interface
     * @return "" (public), "-" (private), "#" (protected) or "@" (package)
     */
    private static String visibilityMarker(Set<Modifier> flags, boolean insideInterface) {
        if (insideInterface) {
            return "";
        }
        if (flags.contains(Modifier.PUBLIC)) {
            return "";
        }
        if (flags.contains(Modifier.PRIVATE)) {
            return "-";
        }
        if (flags.contains(Modifier.PROTECTED)) {
            return "#";
        }
        return "@";
    }

    /**
     * Build the start of a member line: visibility marker (if any) + '$' if
     * static + the name. A public member whose name collides with a Veltro
     * keyword keeps an explicit '+'.
     *
     * @param name     the member name
     * @param marker   the visibility marker from {@link #visibilityMarker}
     * @param isStatic whether the member is static
     * @return e.g. 'token', '- _secret', '$make', '+ module'
     */
    private static String memberPrefix(String name, String marker, boolean isStatic) {
        String core = (isStatic ? "$" : "") + name;
        if (marker.isEmpty()) {
            if (RESERVED_NAMES.contains(name)) {
                return "+ " + core;
            }
            return core;
        }
        return marker + " " + core;
    }

    // ============ MEMBER EXTRACTION ============

    /**
     * Whether a field initializer is a plain literal, safe to copy verbatim
     * after the '='.
     *
     * Anything else -- a method call, a lambda, an anonymous class -- renders
     * via toString() as arbitrary, often multi-line Java source, which would
     * inject newlines and stray '(' into the line-oriented .vel and corrupt it.
     * (Real example from Spring: a field assigned 'new SomeInterface() { ... }'
     * dumped a whole method body into the model.) For those, the default is
     * dropped: a default value is informative, not load-bearing.
     *
     * @param init the initializer expression
     * @return true only for numeric / boolean / char / string / null literals
     */
    private static boolean isSimpleDefault(ExpressionTree init) {
        switch (init.getKind()) {
            case INT_LITERAL:
            case LONG_LITERAL:
            case FLOAT_LITERAL:
            case DOUBLE_LITERAL:
            case BOOLEAN_LITERAL:
            case CHAR_LITERAL:
            case STRING_LITERAL:
            case NULL_LITERAL:
                return true;
            default:
                return false;
        }
    }

    /**
     * Turn a field declaration into a Veltro field line.
     *
     * @param field           the variable declaration
     * @param insideInterface true when the field belongs to an interface
     * @return the field line, e.g. 'expires int?' or '- _cache Map<String,Object>'
     */
    private static String extractField(VariableTree field, boolean insideInterface) {
        Set<Modifier> flags = field.getModifiers().getFlags();
        String marker = visibilityMarker(flags, insideInterface);
        boolean isStatic = flags.contains(Modifier.STATIC);

        String name = field.getName().toString();
        String type = javaTypeToVeltro(field.getType());

        String line = memberPrefix(name, marker, isStatic) + " " + type;
        if (field.getInitializer() != null && isSimpleDefault(field.getInitializer())) {
            line += " = " + field.getInitializer().toString();
        }
        return line;
    }

    /**
     * Collect a method's parameters as Veltro 'name Type' tokens. Java always
     * names and types its parameters, so (unlike the Python extractor) no 'Any'
     * fallback is ever needed.
     *
     * @param method the method (or constructor) declaration
     * @return e.g. ['raw Map<String,Object>', 'ttl int']
     */
    private static List<String> methodArguments(MethodTree method) {
        List<String> tokens = new ArrayList<String>();
        for (VariableTree parameter : method.getParameters()) {
            String name = parameter.getName().toString();
            String type = javaTypeToVeltro(parameter.getType());
            tokens.add(name + " " + type);
        }
        return tokens;
    }

    /**
     * Turn a method or constructor into a Veltro method line. A constructor
     * (javac names it '<init>') is emitted under the class's own name and, like
     * any void method, carries no return type.
     *
     * @param method          the method or constructor declaration
     * @param className       the simple name of the enclosing type
     * @param insideInterface true when the method belongs to an interface
     * @return the method line, e.g. 'refresh(ttl int)' or '$make(raw Map<String,Object>) Session'
     */
    private static String extractMethod(MethodTree method, String className, boolean insideInterface) {
        Set<Modifier> flags = method.getModifiers().getFlags();
        String marker = visibilityMarker(flags, insideInterface);
        boolean isStatic = flags.contains(Modifier.STATIC);

        String name = method.getName().toString();
        boolean isConstructor = name.equals("<init>");
        if (isConstructor) {
            name = className;
        }

        List<String> arguments = methodArguments(method);
        String line = memberPrefix(name, marker, isStatic) + "(" + String.join(", ", arguments) + ")";

        // Constructors and void methods carry no return type.
        if (!isConstructor) {
            String returnType = javaTypeToVeltro(method.getReturnType());
            if (!returnType.equals("void")) {
                line += " " + returnType;
            }
        }
        return line;
    }

    // ============ TYPE (CLASS / INTERFACE / ENUM) EXTRACTION ============

    /**
     * Whether a member is an enum constant (as opposed to an ordinary field).
     *
     * The public Tree API does not expose the enum-constant flag, so we read it
     * straight from javac's own tree node: this is the same authoritative bit
     * the compiler uses, not a heuristic.
     *
     * @param member a type member
     * @return true if it is an enum constant
     */
    private static boolean isEnumConstant(Tree member) {
        if (!(member instanceof JCTree.JCVariableDecl)) {
            return false;
        }
        JCTree.JCVariableDecl declaration = (JCTree.JCVariableDecl) member;
        return (declaration.mods.flags & Flags.ENUM) != 0;
    }

    /**
     * Decide the Veltro kind keyword for a type from its tree kind and
     * modifiers. An annotation type (@interface) is modelled as an interface.
     *
     * @param type the type declaration
     * @return 'enum', 'interface', 'class' or 'class abstract'
     */
    private static String classifyKind(ClassTree type) {
        Tree.Kind kind = type.getKind();
        if (kind == Tree.Kind.ENUM) {
            return "enum";
        }
        if (kind == Tree.Kind.INTERFACE || kind == Tree.Kind.ANNOTATION_TYPE) {
            return "interface";
        }
        if (type.getModifiers().getFlags().contains(Modifier.ABSTRACT)) {
            return "class abstract";
        }
        return "class";
    }

    /**
     * Emit the single 'enum Name = A, B, C' line for an enum type.
     *
     * @param type the enum declaration
     * @return the one-line list (so callers can extend a shared list uniformly)
     */
    private static List<String> extractEnum(ClassTree type) {
        List<String> values = new ArrayList<String>();
        for (Tree member : type.getMembers()) {
            if (isEnumConstant(member)) {
                values.add(((VariableTree) member).getName().toString());
            }
        }
        List<String> lines = new ArrayList<String>();
        lines.add("enum " + type.getSimpleName().toString() + " = " + String.join(", ", values));
        return lines;
    }

    /**
     * Record the inheritance edges of a type.
     *
     * 'extends' on a class becomes an 'extend' edge. The 'implements' list
     * becomes 'impl' edges for a class/enum, but 'extend' edges for an
     * interface (where that list actually holds the super-interfaces).
     *
     * @param type  the type declaration
     * @param kind  the Veltro kind keyword from {@link #classifyKind}
     * @param edges the running list of edges to append to
     */
    private static void collectEdges(ClassTree type, String kind, List<Edge> edges) {
        String childName = type.getSimpleName().toString();

        Tree superclass = type.getExtendsClause();
        if (superclass != null) {
            String baseName = simpleName(superclass);
            if (!IGNORED_BASES.contains(baseName)) {
                edges.add(new Edge(childName, "extend", baseName));
            }
        }

        boolean isInterface = kind.equals("interface");
        for (Tree implemented : type.getImplementsClause()) {
            String baseName = simpleName(implemented);
            if (IGNORED_BASES.contains(baseName)) {
                continue;
            }
            String edgeKind = isInterface ? "extend" : "impl";
            edges.add(new Edge(childName, edgeKind, baseName));
        }
    }

    /**
     * Turn one top-level type declaration into its Veltro lines, appending any
     * inheritance edges to the shared list.
     *
     * @param type  the type declaration
     * @param edges the running list of edges to append to
     * @return the declaration line plus its member lines
     */
    private static List<String> extractType(ClassTree type, List<Edge> edges) {
        String kind = classifyKind(type);
        collectEdges(type, kind, edges);

        if (kind.equals("enum")) {
            return extractEnum(type);
        }

        boolean insideInterface = kind.equals("interface");
        String className = type.getSimpleName().toString();

        List<String> lines = new ArrayList<String>();
        lines.add(kind + " " + className);

        for (Tree member : type.getMembers()) {
            if (member instanceof VariableTree) {
                lines.add(extractField((VariableTree) member, insideInterface));
            } else if (member instanceof MethodTree) {
                lines.add(extractMethod((MethodTree) member, className, insideInterface));
            }
            // Nested types, initializer blocks, etc. are skipped (see header).
        }
        return lines;
    }

    // ============ PROJECT WALK & RENDERING ============

    /**
     * Collect every .java file under a directory, recursively.
     *
     * @param directory the root to scan
     * @param collected the list to append discovered files to
     */
    private static void collectJavaFiles(File directory, List<File> collected) {
        File[] entries = directory.listFiles();
        if (entries == null) {
            return;
        }
        Arrays.sort(entries);
        for (File entry : entries) {
            if (entry.isDirectory()) {
                collectJavaFiles(entry, collected);
            } else if (entry.getName().endsWith(".java")) {
                collected.add(entry);
            }
        }
    }

    /**
     * The dotted module path for a compilation unit: its package name, or
     * 'default' for the unnamed package.
     *
     * @param unit a parsed source file
     * @return the module path
     */
    private static String moduleOf(CompilationUnitTree unit) {
        if (unit.getPackageName() == null) {
            return "default";
        }
        return unit.getPackageName().toString();
    }

    /**
     * Assemble the final '.vel' text from the per-module type lines and the
     * global edges, mirroring the Python extractor's render_vel.
     *
     * @param modules  package -> its accumulated type lines (insertion order)
     * @param allEdges every inheritance edge found across all files
     * @return the complete '.vel' document
     */
    private static String renderVel(Map<String, List<String>> modules, List<Edge> allEdges) {
        StringBuilder out = new StringBuilder();
        out.append("veltro 1\n\n");

        for (Map.Entry<String, List<String>> entry : modules.entrySet()) {
            List<String> typeLines = entry.getValue();
            if (typeLines.isEmpty()) {
                continue;
            }
            out.append("module ").append(entry.getKey()).append("\n");
            for (String line : typeLines) {
                out.append(line).append("\n");
            }
            out.append("\n");
        }

        if (!allEdges.isEmpty()) {
            out.append("rel\n");
            for (Edge edge : allEdges) {
                out.append(edge.from).append(" ").append(edge.kind).append(" ").append(edge.to).append("\n");
            }
            out.append("\n");
        }

        // Trim trailing blank lines down to a single closing newline.
        String text = out.toString();
        int end = text.length();
        while (end > 0 && (text.charAt(end - 1) == '\n' || text.charAt(end - 1) == ' ')) {
            end--;
        }
        return text.substring(0, end) + "\n";
    }

    // ============ ENTRY POINT ============

    public static void main(String[] arguments) throws IOException {
        String sourceDir = null;
        String outPath = null;

        for (int index = 0; index < arguments.length; index++) {
            String argument = arguments[index];
            if (argument.equals("--out") && index + 1 < arguments.length) {
                outPath = arguments[index + 1];
                index++;
            } else if (sourceDir == null) {
                sourceDir = argument;
            }
        }

        if (sourceDir == null) {
            System.err.println("usage: java VeltroJavaExtractor <src_dir> [--out file.vel]");
            System.exit(2);
            return;
        }

        List<File> javaFiles = new ArrayList<File>();
        collectJavaFiles(new File(sourceDir), javaFiles);
        if (javaFiles.isEmpty()) {
            System.err.println("[ERROR] - no .java files found under " + sourceDir);
            System.exit(1);
            return;
        }

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            System.err.println("[ERROR] - no system Java compiler; run this with a JDK, not a JRE");
            System.exit(1);
            return;
        }

        // Parse only: purely syntactic, so no classpath / target build needed.
        // The diagnostic listener is null, so any parse notes go to stderr and
        // never corrupt the .vel written to stdout/--out.
        StandardJavaFileManager fileManager = compiler.getStandardFileManager(null, null, StandardCharsets.UTF_8);
        Iterable<? extends JavaFileObject> sources = fileManager.getJavaFileObjectsFromFiles(javaFiles);
        JavacTask task = (JavacTask) compiler.getTask(null, fileManager, null, null, null, sources);

        Map<String, List<String>> modules = new LinkedHashMap<String, List<String>>();
        List<Edge> allEdges = new ArrayList<Edge>();
        int typeCount = 0;

        for (CompilationUnitTree unit : task.parse()) {
            String module = moduleOf(unit);
            List<String> moduleLines = modules.get(module);
            if (moduleLines == null) {
                moduleLines = new ArrayList<String>();
                modules.put(module, moduleLines);
            }
            for (Tree declaration : unit.getTypeDecls()) {
                if (declaration instanceof ClassTree) {
                    moduleLines.addAll(extractType((ClassTree) declaration, allEdges));
                    typeCount++;
                }
            }
        }
        fileManager.close();

        String vel = renderVel(modules, allEdges);

        // Stats go to stderr so a plain '> file.vel' redirect stays clean.
        PrintStream report = System.err;
        report.println("[INFO] - files: " + javaFiles.size());
        report.println("[INFO] - modules: " + modules.size());
        report.println("[INFO] - types: " + typeCount);
        report.println("[INFO] - edges: " + allEdges.size());

        if (outPath != null) {
            Files.write(new File(outPath).toPath(), vel.getBytes(StandardCharsets.UTF_8));
            report.println("[INFO] - written: " + outPath);
        } else {
            System.out.print(vel);
        }
    }
}
