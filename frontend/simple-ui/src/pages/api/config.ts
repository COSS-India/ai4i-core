import type { NextApiRequest, NextApiResponse } from "next";
import {
  getServerRuntimeConfig,
  type RuntimeConfig,
} from "../../config/runtimeConfig";

/**
 * Public runtime config for the browser.
 * Values come from the pod/process env (ConfigMap) at request time — not from
 * the Docker build — so ENABLED_TASK_TYPES / API_URL / TELEMETRY_SERVICE_URL /
 * PLATFORM_NAME can change without rebuilding the image.
 */
export default function handler(
  req: NextApiRequest,
  res: NextApiResponse<RuntimeConfig | { error: string }>,
) {
  if (req.method !== "GET") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  res.setHeader("Cache-Control", "no-store");
  return res.status(200).json(getServerRuntimeConfig());
}
