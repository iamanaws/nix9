# Session namespaces

Use `namespace.binds` to arrange local directories, package outputs and
[mounted shares](sharing.md) into a session's filesystem view. For example,
combine projects from a file server with tools from another machine:

```nix
{
  directories."/usr/glenda/work".mode = "0750";
  namespace.binds = [
    {
      source = "/n/projects";
      target = "/usr/glenda/work";
      create = true;
    }
    {
      source = "/n/tools";
      target = "/usr/glenda/work";
      mode = "append";
    }
  ];
}
```

Both shares must be declared in `namespace.mounts`, directly or through an
[installation inventory](installation.md). This view searches projects first,
then tools. New files go to projects. The underlying `work` directory and its
contents remain on disk.

## Order and creation

Entries run in list order, after shares connect. Repeating a target builds a
native union directory:

| `mode` | Effect |
| --- | --- |
| `"replace"`, the default | Replace the target's current view with the source. |
| `"prepend"` | Search the source before the current entries. |
| `"append"` | Search the source after the current entries. |

A later prepend takes precedence over earlier entries. A later replace discards
their view. Module imports merge these lists; use `lib.mkBefore` and `lib.mkAfter`
to control their order. A source can refer to a target arranged by earlier entries.

`create` defaults to `false`. Set it on entries that may receive new files;
the first eligible entry receives them. It does not make existing files
read-only. Native permissions and export policy still apply. Native `bind`
restricts `create = true` on union sources. Use the original source directories
when choosing where new files go.

## Paths and availability

Sources and targets are canonical absolute paths. Package sources such as
`source = "${pkgs.fortune}/bin";` retain their Nix dependencies. Keep the package
reference in the expression rather than copying a literal store path.

Targets must already be directories or have a
[directory declaration](configuration.md#persistent-directories). Preparation
changes the underlying directory's metadata before applying session bindings.
Targets cannot nest, overlap session mount points, or cover native namespace
paths, Nix state or generated system files. A source and its own target cannot
contain one another. Directory declarations below a binding target are rejected.

`required` defaults to `true`. An unavailable source fails refresh and prevents
a new login from executing its command. With `required = false`, activation
reports the missing source and skips that entry. A source under an unavailable
optional share is also unavailable. Refresh retries skipped entries.

## Refresh and rollback

Bindings apply at login or `. /usr/local/pkg/nix9/system` refresh. Boot services
keep their native namespaces. Existing sessions retain their views when another
session refreshes. Selecting or rolling back a generation requires a refresh to
change the current shell's view.

Refresh checks managed bindings and stages the new view before replacing it.
A failed connection or binding restores the previous session mounts and bindings.
Manual bindings at declared targets, changes to managed union entries and changes
to their private anchors fail the check. Unchanged activation reuses the view.
Removing a binding restores the underlying directory on refresh.

Rollback changes the namespace and reapplies declared directory metadata. It
does not restore file contents. Keep generations used by existing sessions
[retained through GC](configuration.md#generations).
