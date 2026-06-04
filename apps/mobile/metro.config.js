// Metro config for a pnpm monorepo.
// - watch the repo root so changes in packages/shared trigger reloads
// - let Metro resolve modules from both the app and the root node_modules
//   (pnpm hoists shared deps to the root .pnpm store + root node_modules)
const { getDefaultConfig } = require("expo/metro-config");
const path = require("path");

const projectRoot = __dirname;
const workspaceRoot = path.resolve(projectRoot, "../..");

const config = getDefaultConfig(projectRoot);

config.watchFolders = [workspaceRoot];
config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, "node_modules"),
  path.resolve(workspaceRoot, "node_modules"),
];
// pnpm uses symlinks; ensure Metro follows them rather than duplicating modules.
config.resolver.disableHierarchicalLookup = false;

module.exports = config;
