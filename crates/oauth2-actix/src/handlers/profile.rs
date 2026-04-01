use actix_session::Session;
use actix_web::{HttpResponse, Result};

/// Render the user profile page.
///
/// Reads session data (user_id, username, email, role, user_info) and renders
/// an HTML page showing the authenticated user's information. If the user is
/// not logged in, redirects to `/auth/login`.
pub async fn profile_page(session: Session) -> Result<HttpResponse> {
    let authenticated: Option<bool> = session.get("authenticated").unwrap_or(None);

    if !authenticated.unwrap_or(false) {
        return Ok(HttpResponse::Found()
            .append_header(("Location", "/auth/login"))
            .finish());
    }

    let user_id = session
        .get::<String>("user_id")
        .unwrap_or(None)
        .unwrap_or_default();
    let username = session
        .get::<String>("username")
        .unwrap_or(None)
        .unwrap_or_default();
    let email = session
        .get::<String>("email")
        .unwrap_or(None)
        .unwrap_or_else(|| "—".to_string());
    let role = session
        .get::<String>("role")
        .unwrap_or(None)
        .unwrap_or_else(|| "user".to_string());
    let social_info_json: Option<String> = session.get("user_info").unwrap_or(None);

    // Role badge styling
    let role_class = if role == "admin" {
        "bg-purple-100 text-purple-800"
    } else {
        "bg-blue-100 text-blue-800"
    };

    // Build social login section if social info is present
    let social_section = if let Some(ref json_str) = social_info_json {
        build_social_section(json_str)
    } else {
        String::new()
    };

    // Admin link (only for admins)
    let admin_link = if role == "admin" || is_admin_email(&email) {
        r#"<a href="/admin" class="flex items-center gap-3 p-3 rounded-lg border border-gray-200 hover:bg-gray-50 transition-colors">
            <div class="flex items-center justify-center w-8 h-8 bg-purple-100 rounded-lg">
              <svg class="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path>
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
              </svg>
            </div>
            <span class="text-sm font-medium text-gray-700">Admin Dashboard</span>
          </a>"#.to_string()
    } else {
        String::new()
    };

    // Load template and replace placeholders
    let html = std::fs::read_to_string("templates/profile.html")
        .unwrap_or_else(|_| fallback_profile_html())
        .replace("{{USERNAME}}", &html_escape(&username))
        .replace("{{EMAIL}}", &html_escape(&email))
        .replace("{{ROLE}}", &html_escape(&role))
        .replace("{{ROLE_CLASS}}", role_class)
        .replace("{{USER_ID}}", &html_escape(&user_id))
        .replace("{{SOCIAL_SECTION}}", &social_section)
        .replace("{{ADMIN_LINK}}", &admin_link);

    Ok(HttpResponse::Ok()
        .content_type("text/html; charset=utf-8")
        .body(html))
}

fn is_admin_email(email: &str) -> bool {
    if let Ok(admin_emails) = std::env::var("OAUTH2_ADMIN_EMAILS") {
        let email_lower = email.to_lowercase();
        return admin_emails
            .split(',')
            .map(|e| e.trim().to_lowercase())
            .any(|e| e == email_lower);
    }
    false
}

/// Build the social login info HTML card.
fn build_social_section(json_str: &str) -> String {
    #[derive(serde::Deserialize)]
    struct SocialInfo {
        provider: Option<String>,
        provider_user_id: Option<String>,
        email: Option<String>,
        name: Option<String>,
        picture: Option<String>,
    }

    let info: SocialInfo = match serde_json::from_str(json_str) {
        Ok(i) => i,
        Err(_) => return String::new(),
    };

    let provider = info.provider.unwrap_or_default();
    let provider_display = match provider.as_str() {
        "github" => "GitHub",
        "google" => "Google",
        "microsoft" => "Microsoft",
        "azure" => "Azure AD",
        other => other,
    };

    // Provider icon colour
    let (icon_bg, icon_text) = match provider.as_str() {
        "github" => ("bg-gray-800", "text-white"),
        "google" => ("bg-red-100", "text-red-600"),
        "microsoft" | "azure" => ("bg-blue-100", "text-blue-600"),
        _ => ("bg-gray-100", "text-gray-600"),
    };

    let picture_html = if let Some(ref url) = info.picture {
        format!(
            r#"<img src="{}" alt="avatar" class="w-10 h-10 rounded-full border-2 border-white shadow" />"#,
            html_escape(url)
        )
    } else {
        String::new()
    };

    let name_row = info
        .name
        .as_deref()
        .map(|n| {
            format!(
                r#"<div class="flex items-center justify-between py-3 border-b border-gray-100">
                <span class="text-sm font-medium text-gray-500">Display Name</span>
                <span class="text-sm font-semibold text-gray-900">{}</span>
              </div>"#,
                html_escape(n)
            )
        })
        .unwrap_or_default();

    let social_email_row = info
        .email
        .as_deref()
        .map(|e| {
            format!(
                r#"<div class="flex items-center justify-between py-3 border-b border-gray-100">
                <span class="text-sm font-medium text-gray-500">Provider Email</span>
                <span class="text-sm font-semibold text-gray-900">{}</span>
              </div>"#,
                html_escape(e)
            )
        })
        .unwrap_or_default();

    let provider_id_row = info
        .provider_user_id
        .as_deref()
        .map(|id| {
            format!(
                r#"<div class="flex items-center justify-between py-3">
                <span class="text-sm font-medium text-gray-500">Provider ID</span>
                <span class="text-xs font-mono text-gray-600">{}</span>
              </div>"#,
                html_escape(id)
            )
        })
        .unwrap_or_default();

    format!(
        r#"<div class="bg-white rounded-2xl shadow-xl p-8 mb-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-6 flex items-center gap-2">
          <div class="flex items-center justify-center w-6 h-6 {icon_bg} rounded {icon_text}">
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
            </svg>
          </div>
          Signed in via {provider_display} {picture_html}
        </h2>
        <div class="space-y-4">
          {name_row}
          {social_email_row}
          {provider_id_row}
        </div>
      </div>"#
    )
}

fn fallback_profile_html() -> String {
    r#"<!DOCTYPE html>
<html>
<head><title>My Profile</title></head>
<body>
    <h1>My Profile</h1>
    <p>Username: {{USERNAME}}</p>
    <p>Email: {{EMAIL}}</p>
    <p>Role: {{ROLE}}</p>
    <a href="/auth/logout">Logout</a>
</body>
</html>"#
        .to_string()
}

/// Minimal HTML entity escaping to prevent XSS.
fn html_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#x27;")
}
