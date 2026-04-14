use actix_web::{web, HttpResponse};

use crate::handlers::wellknown::OidcConfig;

/// OIDC Session Management — check_session_iframe endpoint.
///
/// Returns an HTML page with JavaScript that listens for `postMessage`
/// events from RPs to detect session changes. Per OpenID Connect Session
/// Management 1.0: <https://openid.net/specs/openid-connect-session-1_0.html>
///
/// The RP sends `"<client_id> <session_state>"` and the iframe responds
/// with `"changed"` or `"unchanged"`.
pub async fn check_session_iframe(oidc: web::Data<OidcConfig>) -> HttpResponse {
    let issuer = &oidc.issuer;
    let html = format!(
        r#"<!DOCTYPE html>
<html>
<head><title>OIDC Session Check</title></head>
<body>
<script>
(function() {{
  var defined_origin = "{issuer}";
  window.addEventListener("message", function(e) {{
    try {{
      var parts = e.data.split(" ");
      if (parts.length < 2) {{
        e.source.postMessage("error", e.origin);
        return;
      }}
      var client_id = parts[0];
      var session_state = parts.slice(1).join(" ");

      // Compute expected session state from cookie.
      var cookie_name = "op_browser_state";
      var match = document.cookie.match(new RegExp("(^| )" + cookie_name + "=([^;]+)"));
      var browser_state = match ? match[2] : "";

      // Salt is appended to session_state after a dot.
      var dot = session_state.lastIndexOf(".");
      var salt = dot >= 0 ? session_state.substring(dot + 1) : "";
      var provided_hash = dot >= 0 ? session_state.substring(0, dot) : session_state;

      // Compute hash: SHA-256(client_id + " " + e.origin + " " + browser_state + " " + salt)
      var data = client_id + " " + e.origin + " " + browser_state + " " + salt;
      crypto.subtle.digest("SHA-256", new TextEncoder().encode(data)).then(function(hash) {{
        var bytes = new Uint8Array(hash);
        var hex = "";
        for (var i = 0; i < bytes.length; i++) {{
          hex += bytes[i].toString(16).padStart(2, "0");
        }}
        if (hex === provided_hash) {{
          e.source.postMessage("unchanged", e.origin);
        }} else {{
          e.source.postMessage("changed", e.origin);
        }}
      }});
    }} catch(err) {{
      e.source.postMessage("error", e.origin);
    }}
  }}, false);
}})();
</script>
</body>
</html>"#,
        issuer = issuer
    );
    HttpResponse::Ok()
        .content_type("text/html; charset=utf-8")
        .body(html)
}
