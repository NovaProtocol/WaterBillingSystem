/** Tailwind for WaterBillingSystem (all portals). Palette from the CDN kit. */
module.exports = {
  content: [
    "./shared/templates/**/*.html",
    "./shared/static/**/*.js",
    "./landing-page/templates/**/*.html",
    "./customer-portal/templates/**/*.html",
    "./staff-portal/templates/**/*.html",
    "./developer-portal/templates/**/*.html",
  ],
  theme: {
    extend: {
      colors: {
        ui: {
          surface: "var(--ui-surface)",
          "on-surface": "var(--ui-on-surface)",
          variant: "var(--ui-surface-variant)",
          "on-variant": "var(--ui-on-surface-variant)",
          outline: "var(--ui-outline)",
          primary: "var(--ui-primary)",
          error: "var(--ui-error)",
        },
      },
    },
  },
  plugins: [],
};
