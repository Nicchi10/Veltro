# Veltro grammar (syntax highlighting)

The canonical, editor-agnostic definition of how Veltro source is tokenised
for colour. It is a language asset, a sibling of [`SPEC.md`](../SPEC.md): when the
grammar changes, it changes in the same commit, so it never drifts from the spec.

```
grammars/
  veltro.tmLanguage.json       the TextMate grammar (token scopes)
  language-configuration.json  comments (>), brackets, auto-close
```


## Brand colour

Paste this into VS Code `settings.json` (User or Workspace):

```jsonc
"editor.tokenColorCustomizations": {
  "textMateRules": [
    { "scope": ["keyword.control.veltro", "keyword.control.module.veltro", "keyword.operator.relation.veltro"],
      "settings": { "foreground": "#ff5b00", "fontStyle": "bold" } },
    { "scope": ["keyword.operator.optional.veltro", "keyword.operator.union.veltro", "storage.modifier.veltro", "storage.modifier.static.veltro", "constant.language.veltro"],
      "settings": { "foreground": "#ff8c4d" } },
    { "scope": ["entity.name.type.veltro", "support.type.veltro", "entity.name.namespace.veltro"],
      "settings": { "foreground": "#ffae80" } },
    { "scope": ["entity.name.function.veltro"],
      "settings": { "foreground": "#e8b07a" } },
    { "scope": ["constant.other.enum.veltro"],
      "settings": { "foreground": "#ffd1b3" } },
    { "scope": ["comment.line.documentation.veltro"],
      "settings": { "foreground": "#7d8590", "fontStyle": "italic" } }
  ]
}
```

Member names (`variable.other.member.veltro`) are left to the theme foreground on
purpose, so the page does not turn entirely orange.

## Trying it now (before the extension repo exists)

The grammar only gets applied to `.vel` files when an extension contributes it.
For a quick local test, make a throwaway dev extension that points at these files

```json
{
  "name": "veltro-vscode-dev",
  "publisher": "local",
  "version": "0.0.1",
  "engines": { "vscode": "^1.70.0" },
  "contributes": {
    "languages": [
      { "id": "veltro", "extensions": [".vel"], "configuration": "./language-configuration.json" }
    ],
    "grammars": [
      { "language": "veltro", "scopeName": "source.veltro", "path": "./veltro.tmLanguage.json" }
    ]
  }
}
```

Put that `package.json` next to copies of the two grammar files, open the folder
in VS Code, and press F5 (Extension Development Host). Open a `.vel` file and
add the colour snippet above.

## Scopes the grammar emits

| scope | what it marks |
|-------|---------------|
| `keyword.control.veltro` | `veltro` `module` `class` `interface` `enum` `rel` |
| `keyword.operator.relation.veltro` | `extend` `impl` `depend` `assoc` `aggregate` `compose` |
| `storage.modifier.veltro` | `abstract` `sealed` `static` on a declaration |
| `storage.modifier.static.veltro` | the `$` static prefix |
| `entity.name.type.veltro` | a declared type name and relation endpoints |
| `entity.name.namespace.veltro` | a module's dotted path |
| `entity.name.function.veltro` | a method name |
| `variable.other.member.veltro` | a field name |
| `support.type.veltro` | a type used in a member or signature |
| `constant.other.enum.veltro` | an enum constant |
| `keyword.operator.optional.veltro` | the trailing `?` |
| `comment.line.documentation.veltro` | a `>` doc line |
