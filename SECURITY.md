# Security Policy

## Reporting Security Issues

We take the security of this project seriously. If you discover a security vulnerability, please do NOT open a public issue.

Instead, please send an email to:
- **Email**: sksahorajali36@gmail.com

Please include:
1. Description of the issue
2. Steps to reproduce
3. Potential impact
4. Proposed patch or mitigation (if available)

We will respond promptly and work on releasing a fix.

## Security Practices in this Repository

- **No Hardcoded Secrets**: This project does not contain or commit API keys, personal access tokens, or sensitive credentials.
- **Local Isolation**: The Timeline Editor server strictly binds to `127.0.0.1` and restricts CORS requests to local origins.
- **Path Traversal Protection**: All file streaming and media loading endpoints validate paths and enforce directory boundaries to prevent arbitrary file access.
- **Safe Execution**: All video encoding and processing commands are run using list-based argument arrays without `shell=True` to eliminate shell injection risks.
- **Git Ignore**: Video outputs, large files, environment files, and build caches are excluded from version control.
