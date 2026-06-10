import { NextRequest, NextResponse } from "next/server";

// Gateway URL from environment or default
const GATEWAY_URL = process.env.GATEWAY_PROXY_TARGET || "http://127.0.0.1:8080";
const DEMO_TOKEN = process.env.NEXT_PUBLIC_DEMO_ACCESS_TOKEN || "demo-access-token";

type RouteContext = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyRequest(request, path);
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyRequest(request, path);
}

export async function PUT(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyRequest(request, path);
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyRequest(request, path);
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyRequest(request, path);
}

async function proxyRequest(request: NextRequest, pathParts: string[]) {
  const path = pathParts.join("/");
  const url = `${GATEWAY_URL}/${path}`;

  // Build headers
  const headers: HeadersInit = {};

  // Forward request headers except for host
  request.headers.forEach((value, key) => {
    if (key.toLowerCase() !== "host") {
      headers[key] = value;
    }
  });

  // Add the demo token for authentication
  headers["Authorization"] = `Bearer ${DEMO_TOKEN}`;

  try {
    const response = await fetch(url, {
      method: request.method,
      headers,
      body: request.body ? await request.text() : undefined,
    });

    // Forward the response
    const responseHeaders: HeadersInit = {};
    response.headers.forEach((value, key) => {
      if (key.toLowerCase() !== "content-length") {
        responseHeaders[key] = value;
      }
    });

    return new NextResponse(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error("Proxy error:", error);
    return NextResponse.json(
      { error: { code: "proxy_error", message: "Failed to connect to gateway" } },
      { status: 502 }
    );
  }
}
