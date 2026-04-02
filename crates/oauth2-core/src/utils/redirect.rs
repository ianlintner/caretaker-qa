//! URL redirect safety validation.

/// Validate that a redirect target is a safe relative path on this server.
///
/// Accepts only paths starting with `/` that are not:
/// - `//` (protocol-relative URLs like `//evil.com`)
/// - `/\` (backslash quirk exploited by some browsers: `/\evil.com`)
/// - Any scheme-bearing string (`scheme:`)
///
/// This prevents open-redirect attacks where a caller-controlled value
/// could redirect users to an attacker's site.
pub fn is_safe_redirect(url: &str) -> bool {
    let url = url.trim();
    // Must start with a single forward-slash
    if !url.starts_with('/') {
        return false;
    }
    // Reject protocol-relative URLs like //evil.com
    if url.starts_with("//") {
        return false;
    }
    // Reject backslash quirk: /\evil.com
    if url.starts_with("/\\") {
        return false;
    }
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn safe_relative_paths_are_accepted() {
        assert!(is_safe_redirect("/"));
        assert!(is_safe_redirect("/profile"));
        assert!(is_safe_redirect(
            "/oauth/authorize?response_type=code&client_id=x"
        ));
    }

    #[test]
    fn absolute_urls_are_rejected() {
        assert!(!is_safe_redirect("https://evil.example.com"));
        assert!(!is_safe_redirect("http://evil.example.com/path"));
    }

    #[test]
    fn protocol_relative_urls_are_rejected() {
        assert!(!is_safe_redirect("//evil.example.com"));
    }

    #[test]
    fn backslash_quirk_is_rejected() {
        assert!(!is_safe_redirect("/\\evil.example.com"));
    }

    #[test]
    fn empty_and_non_slash_are_rejected() {
        assert!(!is_safe_redirect(""));
        assert!(!is_safe_redirect("relative/path"));
        assert!(!is_safe_redirect("javascript:alert(1)"));
    }
}
