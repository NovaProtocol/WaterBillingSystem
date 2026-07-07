const {
  withAndroidManifest,
  withDangerousMod,
  withGradleProperties,
} = require("expo/config-plugins");
const fs = require("fs");
const path = require("path");

function withNetworkSecurityConfig(config) {
  const isDev = process.env.APP_VARIANT === "development";

  config = withDangerousMod(config, [
    "android",
    (config) => {
      const resXmlDir = path.join(
        config.modRequest.platformProjectRoot,
        "app/src/main/res/xml"
      );
      fs.mkdirSync(resXmlDir, { recursive: true });

      const xmlContent = isDev
        ? `<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="true">
        <trust-anchors>
            <certificates src="user" />
            <certificates src="system" />
        </trust-anchors>
    </base-config>
</network-security-config>`
        : `<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="false">
        <trust-anchors>
            <certificates src="system" />
        </trust-anchors>
    </base-config>
</network-security-config>`;

      fs.writeFileSync(
        path.join(resXmlDir, "network_security_config.xml"),
        xmlContent
      );
      return config;
    },
  ]);

  config = withAndroidManifest(config, (config) => {
    const application = config.modResults.manifest.application?.[0]?.$;
    if (application) {
      application["android:networkSecurityConfig"] =
        "@xml/network_security_config";
      application["android:allowBackup"] = "false";
    }
    return config;
  });

  config = withGradleProperties(config, (config) => {
    const hasMinify = config.modResults.find(
      (p) => p.key === "android.enableMinifyInReleaseBuilds"
    );
    if (!hasMinify) {
      config.modResults.push({
        type: "property",
        key: "android.enableMinifyInReleaseBuilds",
        value: "true",
      });
    }
    return config;
  });

  return config;
}

module.exports = withNetworkSecurityConfig;
