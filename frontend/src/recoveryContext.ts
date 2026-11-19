export function recoveryContextParts(
  org: string,
  user: string,
  environment: string,
) {
  if (
    ![org, user].every(
      (value) =>
        typeof value === "string" &&
        value.length > 0 &&
        value.length <= 100 &&
        !/[\u0000-\u001f\u007f]/.test(value),
    ) ||
    typeof environment !== "string" ||
    !/^[a-z][a-z0-9-]{1,31}$/.test(environment)
  )
    throw new Error(
      "Your workspace context is unavailable. Refresh and sign in again.",
    );
  return [org, user, environment].map(encodeURIComponent);
}

export function recoveryPanelKey(me: Record<string, any>) {
  return recoveryContextParts(
    me?.user?.org_id,
    me?.user?.id,
    me?.environment,
  ).join(":");
}
