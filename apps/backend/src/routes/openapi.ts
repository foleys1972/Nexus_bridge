import { Router, type Request, type Response } from "express";
import fs from "node:fs";
import path from "node:path";

export function openapiRouter(): Router {
  const r = Router();

  r.get("/openapi.yaml", (_req: Request, res: Response) => {
    const p = path.resolve(process.cwd(), "openapi.yaml");
    const data = fs.readFileSync(p, "utf8");
    res.type("text/yaml").send(data);
  });

  return r;
}
