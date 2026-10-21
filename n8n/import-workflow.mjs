// Run inside the n8n container. Environment access stays blocked in workflow nodes.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const key = process.env.AUTOMATION_API_KEY ?? "";
const backend = process.env.BEC_GUARD_BACKEND_URL ?? "";
const publish = process.argv.slice(2).includes("--publish");
let directory;
let stage = "configuration";

try {
  if (key.length < 32) throw new Error("missing key");
  const url = new URL(backend);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password ||
      url.search || url.hash || url.pathname !== "/") throw new Error("invalid backend URL");
  const workflow = JSON.parse(readFileSync(fileURLToPath(
    new URL("./workflows/bec-analysis-webhook.json", import.meta.url)), "utf8"));
  workflow.nodes.find(node => node.name === "Configuration")
    .parameters.assignments.assignments[0].value = url.origin;

  directory = mkdtempSync(join(tmpdir(), "bec-guard-import-"));
  const credentialPath = join(directory, "credential.json");
  const workflowPath = join(directory, "workflow.json");
  writeFileSync(credentialPath, JSON.stringify([{
    id: "bec-guard-automation-header", name: "BEC Guard automation", type: "httpHeaderAuth",
    data: { name: "X-BEC-Automation-Key", value: key },
  }]), { mode: 0o600 });
  writeFileSync(workflowPath, JSON.stringify(workflow), { mode: 0o600 });
  stage = "credential import";
  execFileSync("n8n", ["import:credentials", `--input=${credentialPath}`],
    { stdio: "pipe", timeout: 120000 });
  rmSync(credentialPath);
  stage = "workflow import";
  execFileSync("n8n", ["import:workflow", `--input=${workflowPath}`],
    { stdio: "pipe", timeout: 120000 });
  if (publish) {
    stage = "workflow publish";
    execFileSync("n8n", ["publish:workflow", `--id=${workflow.id}`],
      { stdio: "pipe", timeout: 120000 });
  }
  console.log(`Imported ${workflow.id}; ${publish ? "published (restart n8n)" : "inactive"}.`);
} catch {
  // CLI errors can contain configuration. Never echo captured output or secrets.
  console.error(`BEC Guard import failed during ${stage}. Check local configuration and n8n ownership.`);
  process.exitCode = 1;
} finally {
  if (directory) rmSync(directory, { recursive: true, force: true });
}
