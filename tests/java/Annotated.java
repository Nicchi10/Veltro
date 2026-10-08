package app.models;

/*
 * A type whose declaration opens with annotations, because that decides where
 * its span starts: the extractor records the first MODIFIER line (here line 9,
 * the '@Deprecated'), not the 'class' keyword line. The annotations are part of
 * what the type is, so they belong in the span a reader is shown.
 */
@Deprecated
@SuppressWarnings("unused")
public class Annotated {
    String why;
}
