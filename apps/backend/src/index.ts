import express, { type Request, type Response } from "express";
import cors from "cors";
import http from "http";
import { WebSocketServer } from "ws";
import rateLimit from "express-rate-limit";
import { loadConfig } from "./lib/config.js";
import { ensureDataDir, initDb } from "./lib/db.js";
import { ensureAdminUser } from "./lib/bootstrap.js";
import { authRouter } from "./routes/auth.js";
import { sitesRouter } from "./routes/sites.js";
import { logsRouter } from "./routes/logs.js";
import { clientsRouter } from "./routes/clients.js";
import { openapiRouter } from "./routes/openapi.js";
import { attachClientProxy } from "./ws/clientProxy.js";

const config = loadConfig(process.env.CONFIG_PATH);

ensureDataDir();
const db = initDb();
await ensureAdminUser(db);

const app = express();
app.use(cors());
app.use(express.json({ limit: "2mb" }));

app.get("/api/health", (_req: Request, res: Response) => {
  res.json({ ok: true });
});

app.use(
  "/api",
  rateLimit({ windowMs: 60_000, limit: 1000, standardHeaders: true, legacyHeaders: false })
);

app.use("/api/auth", authRouter(db));
app.use("/api/sites", sitesRouter(db));
app.use("/api/logs", logsRouter(config));
app.use("/api/clients", clientsRouter());
app.use("/api", openapiRouter());

const server = http.createServer(app);
server.listen(config.server.port, config.server.host, () => {
  // eslint-disable-next-line no-console
  console.log(`API listening on http://${config.server.host}:${config.server.port}`);
});

const wss = new WebSocketServer({ port: config.server.ws_port });
attachClientProxy({ wss, db, config });
// eslint-disable-next-line no-console
console.log(`Client WSS listening on ws://0.0.0.0:${config.server.ws_port}`);
