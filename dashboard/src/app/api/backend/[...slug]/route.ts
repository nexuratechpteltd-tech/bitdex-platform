import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";
import fs from "fs";

const BACKEND_INTERNAL_URL = process.env.INTERNAL_BACKEND_URL || "http://127.0.0.1:8002";

function resolveMasterKeyBytes(): Buffer {
  let raw = process.env.TAURIC_VAULT_KEY || "";
  if (!raw) {
    try {
      const envContent = fs.readFileSync("/opt/tauric-platform-staging/backend/.env", "utf-8");
      for (const line of envContent.split("\n")) {
        const trimmed = line.trim();
        if (trimmed.startsWith("TAURIC_VAULT_KEY=") && !trimmed.startsWith("#")) {
          raw = trimmed.split("=", 2)[1].trim().replace(/^["\x27]|["\x27]$/g, "");
          break;
        }
      }
    } catch {
      raw = "";
    }
  }
  if (!raw) {
    return Buffer.alloc(0);
  }
  if (/^[0-9a-fA-F]{64}$/.test(raw)) {
    return Buffer.from(raw, "hex");
  }
  return crypto.createHash("sha256").update(raw, "utf-8").digest();
}

function getInternalApiAuthToken(): string {
  const explicit = (process.env.TAURIC_API_AUTH_TOKEN || "").trim();
  if (explicit) return explicit;
  const masterKey = resolveMasterKeyBytes();
  if (masterKey.length === 0) return "";
  return crypto.createHmac("sha256", masterKey).update("tauric-staging-api-auth-v1").digest("hex");
}

function isCredentialSubmission(method: string, slug: string[]): boolean {
  if (method !== "POST" && method !== "PUT") return false;
  const path = (slug || []).join("/").replace(/\/+$/, "");
  if (path === "connections/universal" || path === "connections/profiles" || path === "connections/test" || path === "saas/customer/connections" || path === "saas/customer/connections/test") {
    return true;
  }
  if (path.startsWith("connections/profiles/") && method === "PUT") {
    return true;
  }
  return false;
}

function verifyTransportSecurity(request: NextRequest, method: string, slug: string[]): NextResponse | null {
  if (!isCredentialSubmission(method, slug)) return null;
  const xfProto = (request.headers.get("x-forwarded-proto") || "").trim().toLowerCase();
  const cfVisitor = (request.headers.get("cf-visitor") || "").trim();
  const cfVisitorHttps = cfVisitor.includes('"scheme":"https"') || cfVisitor.includes('https');
  const host = (request.headers.get("host") || "").trim().toLowerCase();
  const isLoopbackHost = host.startsWith("127.0.0.1") || host.startsWith("localhost") || host.startsWith("[::1]");
  const isHttps = xfProto === "https" || cfVisitorHttps || request.nextUrl.protocol === "https:";

  if (!isLoopbackHost && !isHttps) {
    return NextResponse.json(
      {
        detail:
          "Transport security violation: credential submission over unencrypted public HTTP is strictly prohibited. Use HTTPS/TLS or an encrypted loopback tunnel.",
        error_code: "INSECURE_TRANSPORT_BLOCKED",
      },
      { status: 403 }
    );
  }
  return null;
}

function cleanTargetUrl(slug: string[], search: string) {
  if (BACKEND_INTERNAL_URL.includes(":8001")) {
    throw new Error("SAFETY_VIOLATION: Staging proxy is forbidden from targeting production port 8001.");
  }
  let path = slug ? slug.join("/") : "";
  if (path.endsWith("/")) {
    path = path.slice(0, -1);
  }
  return `${BACKEND_INTERNAL_URL}/api/v1/${path}${search}`;
}

function buildBackendHeaders(request?: NextRequest, includeJsonContentType = false): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Tauric-Api-Key": getInternalApiAuthToken(),
  };
  if (includeJsonContentType) {
    headers["Content-Type"] = "application/json";
  }
  if (request) {
    const adminKey = request.headers.get("x-tauric-admin-key");
    if (adminKey) headers["X-Tauric-Admin-Key"] = adminKey;
    const auth = request.headers.get("authorization");
    if (auth) headers["Authorization"] = auth;
  }
  return headers;
}

async function forwardBackendResponse(res: Response) {
  const contentType = res.headers.get("content-type") || "";
  let data: any;

  if (contentType.includes("application/json")) {
    try {
      data = await res.json();
    } catch {
      data = { error: "Failed to parse backend JSON response", status: res.status };
    }
  } else {
    const text = await res.text();
    data = { error: text || "Backend non-JSON response", status: res.status };
  }

  return NextResponse.json(data, { status: res.status });
}

export async function GET(
  request: NextRequest,
  { params }: { params: { slug: string[] } }
) {
  const targetUrl = cleanTargetUrl(params.slug, request.nextUrl.search);

  try {
    const res = await fetch(targetUrl, {
      method: "GET",
      headers: buildBackendHeaders(request, false),
      next: { revalidate: 0 },
    });

    return forwardBackendResponse(res);
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

export async function POST(
  request: NextRequest,
  { params }: { params: { slug: string[] } }
) {
  const transportErr = verifyTransportSecurity(request, "POST", params.slug);
  if (transportErr) return transportErr;

  const targetUrl = cleanTargetUrl(params.slug, "");

  try {
    let body = {};
    try {
      body = await request.json();
    } catch {
      body = {};
    }
    const res = await fetch(targetUrl, {
      method: "POST",
      headers: buildBackendHeaders(request, true),
      body: JSON.stringify(body),
    });

    return forwardBackendResponse(res);
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

export async function PUT(
  request: NextRequest,
  { params }: { params: { slug: string[] } }
) {
  const transportErr = verifyTransportSecurity(request, "PUT", params.slug);
  if (transportErr) return transportErr;

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
      headers: buildBackendHeaders(request, true),
      body: JSON.stringify(body),
    });

    return forwardBackendResponse(res);
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

export async function DELETE(
  request: NextRequest,
  { params }: { params: { slug: string[] } }
) {
  const targetUrl = cleanTargetUrl(params.slug, request.nextUrl.search);

  try {
    const res = await fetch(targetUrl, {
      method: "DELETE",
      headers: buildBackendHeaders(request, false),
    });

    return forwardBackendResponse(res);
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
