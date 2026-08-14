# Generated fixtures

Test suites may create tiny deterministic ONNX graphs, images, labels, bags,
and bundles at runtime under temporary directories.

These artifacts:

- are not product data;
- are not performance or quality evidence;
- must not be committed as binary fixtures.

Keep generators in source control; clean up after tests unless failure
preservation is configured.
