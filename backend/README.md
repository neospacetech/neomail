# neomail backend

FastAPI service for NeoMail. All domain rules live in the Rust engine and are
called through the `neomail_core` extension module; this package handles HTTP,
problem documents, streaming and the NeoSuite runtime surface.

See the repository README for setup.
