const DEFAULT_EVENT_TYPE = "daily-deals";

async function dispatchGitHubWorkflow(env, source) {
  const owner = env.GITHUB_OWNER || "stevembaron";
  const repo = env.GITHUB_REPO || "projects";
  const eventType = env.GITHUB_EVENT_TYPE || DEFAULT_EVENT_TYPE;
  const token = env.GITHUB_TOKEN;

  if (!token) {
    throw new Error("Missing GITHUB_TOKEN secret");
  }

  const response = await fetch(`https://api.github.com/repos/${owner}/${repo}/dispatches`, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      "User-Agent": "daily-deals-cloudflare-scheduler",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({
      event_type: eventType,
      client_payload: {
        source,
        requested_at: new Date().toISOString(),
      },
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`GitHub dispatch failed: ${response.status} ${body}`);
  }
}

export default {
  async scheduled(_controller, env, ctx) {
    ctx.waitUntil(dispatchGitHubWorkflow(env, "cloudflare-cron"));
  },

  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/health") {
      return Response.json({ ok: true });
    }

    if (request.method === "POST" && url.pathname === "/dispatch") {
      const expectedSecret = env.DISPATCH_SECRET;
      const providedSecret = request.headers.get("x-dispatch-secret");
      if (!expectedSecret || providedSecret !== expectedSecret) {
        return new Response("Unauthorized", { status: 401 });
      }

      await dispatchGitHubWorkflow(env, "manual-http");
      return Response.json({ ok: true });
    }

    return new Response("Not found", { status: 404 });
  },
};
