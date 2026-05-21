import { z } from 'zod';

/** GET /roles/list — API uses `role_id`; description is optional. */
export const roleSchema = z
  .object({
    role_id: z.coerce.number().optional(),
    id: z.coerce.number().optional(),
    name: z.string(),
    description: z.string().nullable().optional(),
  })
  .passthrough()
  .transform((d) => ({
    id: (d.id ?? d.role_id) as number,
    name: d.name,
    description: d.description ?? '',
  }));

/** GET /roles/user/{user_id} — API returns only user_id + roles. */
export const userRoleSchema = z.object({
  user_id: z.string(),
  roles: z.array(z.string()),
  username: z.string().optional(),
  email: z.string().optional(),
});

export const roleActionMessageSchema = z.object({
  message: z.string(),
});
