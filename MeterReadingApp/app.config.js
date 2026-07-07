module.exports = ({ config }) => {
  const isDev = process.env.APP_VARIANT === "development";

  return {
    ...config,
    name: isDev ? "MeterReading - Dev" : config.name,
    android: {
      ...config.android,
      package: isDev
        ? "com.projectnova.MeterReadingApp.dev"
        : config.android.package,
    },
  };
};
