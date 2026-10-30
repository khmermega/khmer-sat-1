import { expect, test } from "@playwright/test";

const TOKEN = "e2e-operator-token";
const ADMIN = "e2e-admin-token";

async function signIn(page: import("@playwright/test").Page, token: string) {
  await page.getByRole("button", { name: "Operator sign-in" }).click();
  await page.getByLabel("Operator token").fill(token);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

test("dashboard shows live simulated telemetry with a clear SIMULATION indicator", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("gs-mode")).toHaveText(/SIMULATION/);
  await expect(page.getByText(/Nothing on this screen is real spacecraft data/)).toBeVisible();
  await expect(page.getByTestId("sat-mode")).toHaveText(/NOMINAL/, { timeout: 20_000 });
  await expect(page.getByTestId("kpi-soc")).toContainText("%");
  await expect(page.getByTestId("ground-track")).toContainText("SYNTHETIC DEMO ORBIT");
  await expect(page.getByTestId("ws-state")).toHaveText(/Stream/);
});

test("operator captures an image and it arrives verified in the gallery", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("sat-mode")).toHaveText(/NOMINAL/, { timeout: 20_000 });
  await signIn(page, TOKEN);
  await expect(page.getByRole("banner").getByText("operator", { exact: true })).toBeVisible();
  await page.getByTestId("camera").getByRole("combobox").selectOption("640x480");
  await page.getByRole("button", { name: /Capture now/ }).click();
  const gallery = page.getByTestId("gallery");
  await expect(gallery).toContainText("1 images received", { timeout: 30_000 });
  await expect(gallery.getByText("SIMULATED")).toBeVisible();
  await expect(page.getByTestId("audit")).toContainText("CAPTURE_IMAGE");
  await expect(page.getByTestId("audit")).toContainText("COMPLETED");
});

test("bad token is refused and critical commands require admin ARM + confirm", async ({ page }) => {
  await page.goto("/");
  await signIn(page, "not-a-real-token");
  await expect(page.getByText(/invalid token/)).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();

  await signIn(page, ADMIN);
  const console = page.getByTestId("commands");
  await console.getByRole("combobox").selectOption("REBOOT");
  await console.getByRole("button", { name: /Arm/ }).click();
  await expect(page.getByTestId("arm-confirm")).toBeVisible();
  await page.getByRole("button", { name: /Confirm & transmit/ }).click();
  await expect(page.getByTestId("audit")).toContainText("REBOOT", { timeout: 15_000 });
  await expect(page.getByTestId("events")).toContainText("COMMANDED_REBOOT", { timeout: 15_000 });
});
