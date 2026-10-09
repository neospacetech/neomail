/**
 * NeoMail client module for the neosuite-app shell.
 *
 * - `routes`: screens mounted under `/neomail`.
 * - `widgets`: embeddable views, keyed by widget id.
 * - `context`: what NeoMind may know and do while a NeoMail screen is open.
 */
export * from "./api";
export { context } from "./context";
export type { ContextDescriptor, ContextSnapshot, ProductRoute, WidgetDescriptor } from "./module";
export { ItemsScreen, LifecycleScreen, routes } from "./routes";
export type * from "./types";
export { ItemStatusBadge, widgets, type ItemStatusBadgeProps } from "./widgets";

/** Product id and mount point used by the shell. */
export const product = { id: "neomail", title: "NeoMail", basePath: "/neomail" } as const;
