import { z } from 'zod';

export const roleSchema = z.object({
  id: z.number(),
  name: z.string(),
  description: z.string(),
});

export const userRoleSchema = z.object({
  user_id: z.string(),
  username: z.string(),
  email: z.string(),
  roles: z.array(z.string()),
});

export const roleActionMessageSchema = z.object({
  message: z.string(),
});
