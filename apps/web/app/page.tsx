"use client";

import { useEffect, useState } from "react";

type DependencyStatus = "ok" | "error";

type Diagnostics = {
  postgres: DependencyStatus;
  redis: DependencyStatus;
};

type PageState =
  | { status: "loading" }
  | { status: "success"; data: Diagnostics }
  | { status: "failure"; message: string };

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

export default function HomePage() {
  const [state, setState] = useState<PageState>({ status: "loading" });

  useEffect(() => {
    if (!apiBaseUrl) {
      setState({
        status: "failure",
        message: "NEXT_PUBLIC_API_BASE_URL is not set.",
      });
      return;
    }

    const controller = new AbortController();

    async function loadDiagnostics() {
      try {
        const response = await fetch(`${apiBaseUrl}/health/dependencies`, {
          signal: controller.signal,
        });
        const data = (await response.json()) as Diagnostics;
        if (!response.ok) {
          setState({
            status: "failure",
            message: `API returned ${String(response.status)}. postgres=${data.postgres}, redis=${data.redis}`,
          });
          return;
        }
        setState({ status: "success", data });
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setState({
          status: "failure",
          message: error instanceof Error ? error.message : "Request failed",
        });
      }
    }

    void loadDiagnostics();
    return () => controller.abort();
  }, []);

  return (
    <main>
      <h1>AI Support Hub</h1>
      <p>Local diagnostics. This is not a product dashboard.</p>
      {state.status === "loading" ? <p>Loading API diagnostics…</p> : null}
      {state.status === "success" ? (
        <ul>
          <li>PostgreSQL: {state.data.postgres}</li>
          <li>Redis: {state.data.redis}</li>
        </ul>
      ) : null}
      {state.status === "failure" ? (
        <p role="alert">Diagnostics failed: {state.message}</p>
      ) : null}
    </main>
  );
}
