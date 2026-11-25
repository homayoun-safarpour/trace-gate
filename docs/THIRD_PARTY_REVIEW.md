# Third-party scope and release review

The project keeps its MIT license and existing attribution. The core wheel has
no declared third-party runtime dependencies. This is a practical inventory,
not legal clearance for every possible downstream distribution.

- AgentEvals framing is credited in the README. This is a separate implementation.
- Promptfoo is optional. Its MIT notice is preserved at
  `integrations/promptfoo/licenses/PROMPTFOO-MIT.txt`. The source archive includes
  integration code, examples, a lockfile and evidence, not installed npm packages.
- OpenInference source and specifications were inspected under Apache-2.0. Its
  runtime code is not bundled; the adapter and synthetic fixtures are original.
  Source/version references are in `docs/otel-source-lock.json`.
- The optional npm dependency lock includes LGPL and compound-license entries
  in the Sharp/libvips package family, and missing declared-license metadata for
  `sylvester` and `xmlhttprequest-ssl`. Do not call that entire dependency tree MIT.
  Review actual package notices and redistribution obligations before bundling
  the optional Node runtime in a later deliverable.

The prepared wheel and source archive deliberately exclude `node_modules` and
its platform binaries. Build/test tooling is installed separately. A successful
security audit does not resolve licensing obligations, and a metadata license
inventory is not a substitute for inspecting licenses if redistribution changes.
