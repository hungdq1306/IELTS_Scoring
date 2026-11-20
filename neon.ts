import { defineConfig } from "@neon/config/v1";

// Postgres belongs to the CLI-linked project/branch. The requested init command
// supplies those identifiers; this file does not create a substitute project.
// Applying this policy provisions Managed Better Auth, not the Python web host.
export default defineConfig({
  auth: true,
});
