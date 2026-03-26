import fs from "node:fs";
import path from "node:path";
import YAML from "yaml";
import { z } from "zod";

const ConfigSchema = z.object({
  server: z.object({
    port: z.number().int().positive(),
    ws_port: z.number().int().positive(),
    host: z.string().min(1)
  }),
  logging: z.object({
    base_path: z.string().min(1),
    default_rotation_size_mb: z.number().int().positive(),
    default_retention_days: z.number().int().positive(),
    compression_after_days: z.number().int().positive()
  }),
  security: z.object({
    session_timeout_minutes: z.number().int().positive(),
    max_clients: z.number().int().positive()
  }),
  bt_defaults: z.object({
    heartbeat_interval_seconds: z.number().int().positive(),
    reconnect_attempts: z.number().int().positive(),
    command_timeout_seconds: z.number().int().positive()
  })
});

export type AppConfig = z.infer<typeof ConfigSchema>;

export function loadConfig(configPath?: string): AppConfig {
  const p = configPath ?? path.resolve(process.cwd(), "../../config.yaml");
  const raw = fs.readFileSync(p, "utf8");
  const parsed = YAML.parse(raw);
  return ConfigSchema.parse(parsed);
}
