import { Router, type Request, type Response } from "express";
import { authRequired } from "../middleware/rbac.js";
import { getClientSnapshot } from "../ws/clientProxy.js";

export function clientsRouter(): Router {
  const r = Router();
  r.use(authRequired);

  r.get("/", (_req: Request, res: Response) => {
    res.json(getClientSnapshot());
  });

  return r;
}
