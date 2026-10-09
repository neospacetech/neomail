import type { ProductRoute } from "../module";
import { ItemsScreen } from "./ItemsScreen";
import { LifecycleScreen } from "./LifecycleScreen";

export { ItemsScreen, LifecycleScreen };

/** Screens mounted by the shell under `/neomail`. */
export const routes: ProductRoute[] = [
  { path: "", title: "Items", nav: true, component: ItemsScreen },
  { path: "lifecycle", title: "Lifecycle", nav: true, component: LifecycleScreen },
];
