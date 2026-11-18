type Guard = (continueNavigation: () => void) => void;
let active: Guard | null = null;
export function registerNavigationGuard(guard: Guard) {
  active = guard;
  return () => {
    if (active === guard) active = null;
  };
}
export function requestNavigationGuard(continueNavigation: () => void) {
  if (!active) return false;
  active(continueNavigation);
  return true;
}
