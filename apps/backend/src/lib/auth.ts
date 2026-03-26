import jwt from "jsonwebtoken";
import { z } from "zod";

export type Role = "Admin" | "Operator" | "Viewer";

const JwtPayloadSchema = z.object({
  sub: z.string(),
  role: z.enum(["Admin", "Operator", "Viewer"])
});

export function requireJwtSecret(): string {
  const s = process.env.JWT_SECRET;
  if (!s) throw new Error("JWT_SECRET is required");
  return s;
}

export function signAccessToken(payload: { sub: string; role: Role }): string {
  return jwt.sign(payload, requireJwtSecret(), { expiresIn: "15m" });
}

export function signRefreshToken(payload: { sub: string; role: Role }): string {
  return jwt.sign(payload, requireJwtSecret(), { expiresIn: "7d" });
}

export function verifyToken(token: string): { sub: string; role: Role } {
  const decoded = jwt.verify(token, requireJwtSecret());
  return JwtPayloadSchema.parse(decoded);
}
