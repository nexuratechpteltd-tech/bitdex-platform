import os
import re

ROUTE_PATH = "/opt/tauric-platform-staging/dashboard/src/app/api/backend/[...slug]/route.ts"
DASHBOARD_PATH = "/opt/tauric-platform-staging/dashboard/src/components/UnifiedSignalDashboard.tsx"

# 1. Update route.ts to add PUT
with open(ROUTE_PATH, "r") as f:
    route_content = f.read()

if "export async function PUT" not in route_content:
    put_code = """
export async function PUT(
  request: NextRequest,
  { params }: { params: { slug: string[] } }
) {
  const targetUrl = cleanTargetUrl(params.slug, "");

  try {
    let body = {};
    try {
      body = await request.json();
    } catch {
      body = {};
    }
    const res = await fetch(targetUrl, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
      },
      body: JSON.stringify(body),
    });

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: any) {
    return NextResponse.json(
      {
        error: "Backend unavailable",
        message: err.message,
        target: targetUrl,
      },
      { status: 503 }
    );
  }
}
"""
    route_content = route_content.rstrip() + "\n" + put_code
    with open(ROUTE_PATH, "w") as f:
        f.write(route_content)
    print("Added PUT handler to staging route.ts")
else:
    print("PUT handler already present in staging route.ts")

# 2. Update UnifiedSignalDashboard.tsx in staging
with open(DASHBOARD_PATH, "r") as f:
    dash_content = f.read()

# Replace endpoint URLs with trailing slashes
dash_content = dash_content.replace(
    'fetch("/trading/api/backend/connections/profiles")',
    'fetch("/trading/api/backend/connections/profiles/")'
)
dash_content = dash_content.replace(
    'fetch("/trading/api/backend/connections/profiles"',
    'fetch("/trading/api/backend/connections/profiles/"'
)
dash_content = dash_content.replace(
    'fetch(`/trading/api/backend/connections/profiles/${profileId}/toggle-read-only`',
    'fetch(`/trading/api/backend/connections/profiles/${profileId}/toggle-read-only/`'
)
dash_content = dash_content.replace(
    'fetch(`/trading/api/backend/connections/profiles/${editingProfileId}`',
    'fetch(`/trading/api/backend/connections/profiles/${editingProfileId}/`'
)
dash_content = dash_content.replace(
    'fetch(`/trading/api/backend/connections/profiles/${profileId}/disconnect`',
    'fetch(`/trading/api/backend/connections/profiles/${profileId}/disconnect/`'
)
dash_content = dash_content.replace(
    'fetch("/trading/api/backend/connections/test"',
    'fetch("/trading/api/backend/connections/test/"'
)
dash_content = dash_content.replace(
    'fetch(`/trading/api/backend/connections/profiles/${profileId}`',
    'fetch(`/trading/api/backend/connections/profiles/${profileId}/`'
)

# Enhance auto-verification on save:
old_save_block = """        const res = await fetch("/trading/api/backend/connections/profiles/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            exchange: effectiveExch,
            environment: newConn.environment,
            environment_preference: newConn.environmentPreference,
            is_read_only: newConn.isReadOnly,
            label: newConn.label,
            api_key: newConn.apiKey,
            api_secret: newConn.apiSecret,
            passphrase: newConn.passphrase || undefined,
            custom_config: customConfig,
          }),
        });
        const data = await res.json();
        if (res.ok) {
          setConnMessage(`Saved ${newConn.environment} profile for ${effectiveExch}. Vault encryption verified.`);
          resetConnForm();
          await fetchConnections();
        }"""

new_save_block = """        const res = await fetch("/trading/api/backend/connections/profiles/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            exchange: effectiveExch,
            environment: newConn.environment,
            environment_preference: newConn.environmentPreference,
            is_read_only: newConn.isReadOnly,
            label: newConn.label,
            api_key: newConn.apiKey,
            api_secret: newConn.apiSecret,
            passphrase: newConn.passphrase || undefined,
            custom_config: customConfig,
          }),
        });
        const data = await res.json();
        if (res.ok) {
          const newProfileId = data.profile?.profile_id;
          if (newProfileId && testResult && testResult.status === "PASS") {
            try {
              await fetch(`/trading/api/backend/connections/profiles/${newProfileId}/retest/`, { method: "POST" });
            } catch {
              // Non-blocking sync
            }
          }
          setConnMessage(`Saved ${newConn.environment} profile for ${effectiveExch}. Vault encryption verified.`);
          resetConnForm();
          await fetchConnections();
        }"""

if old_save_block in dash_content:
    dash_content = dash_content.replace(old_save_block, new_save_block)
    print("Enhanced save handler in staging UnifiedSignalDashboard.tsx")

# Enhance diagnostic test result title & badge
old_probe_title = """                    <div className="flex items-center gap-2">
                      <span className="font-bold text-white text-sm">Connection Status:</span>
                      <span
                        className={`px-2.5 py-0.5 rounded-full font-mono text-xs font-bold ${"""

new_probe_title = """                    <div className="flex items-center gap-2">
                      <span className="font-bold text-white text-sm">
                        {testingProfileId && testingProfileId !== "manual"
                          ? "Retest Verification Result:"
                          : "Pre-Save Diagnostic Test Result:"}
                      </span>
                      <span
                        className={`px-2.5 py-0.5 rounded-full font-mono text-xs font-bold ${"""

if old_probe_title in dash_content:
    dash_content = dash_content.replace(old_probe_title, new_probe_title)
    print("Updated probe title in staging UnifiedSignalDashboard.tsx")

# Add badge clarifying ephemeral test probe
old_status_close = """                        {testResult.connection_status || testResult.verification_label || testResult.status}
                      </span>
                    </div>"""

new_status_close = """                        {testResult.connection_status || testResult.verification_label || testResult.status}
                      </span>
                      {(!testingProfileId || testingProfileId === "manual") && (
                        <span className="text-[10px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded-md border border-slate-700">
                          Temporary Diagnostic Probe (Credentials Not Yet Saved)
                        </span>
                      )}
                    </div>"""

if old_status_close in dash_content:
    dash_content = dash_content.replace(old_status_close, new_status_close)
    print("Added ephemeral test badge in staging UnifiedSignalDashboard.tsx")

with open(DASHBOARD_PATH, "w") as f:
    f.write(dash_content)

print("UnifiedSignalDashboard.tsx updated in staging.")
