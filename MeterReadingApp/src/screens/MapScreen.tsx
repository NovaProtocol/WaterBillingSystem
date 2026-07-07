import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { WebView } from 'react-native-webview';
import { getCustomersWithCoordinates, type CustomerRow } from '@/db/database';
import { useNavigation } from '@react-navigation/native';

function buildMapHtml(customers: CustomerRow[]): string {
  const markers = customers.map((c) => ({
    lat: c.x_coordinate,
    lng: c.y_coordinate,
    name: c.name,
    num: c.customer_number,
    addr: c.address ?? '',
    lastVal: c.last_reading_value,
  }));

  return `
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    * { margin:0; padding:0; }
    html, body, #map { width: 100%; height: 100%; }
  </style>
</head>
<body>
  <div id="map"></div>
  <script>
    var map = L.map('map', { zoomControl: true });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '© OpenStreetMap'
    }).addTo(map);

    var markers = ${JSON.stringify(markers)};
    var bounds = [];
    var icon = L.divIcon({
      html: '<div style="background:#e94560;color:#fff;border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:bold;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,0.3)">●</div>',
      className: '',
      iconSize: [20, 20],
      iconAnchor: [10, 10],
    });

    for (var i = 0; i < markers.length; i++) {
      var m = markers[i];
      if (!m.lat || !m.lng) continue;
      var lat = parseFloat(m.lat);
      var lng = parseFloat(m.lng);
      var popup = '<b>' + m.name + '</b><br/>' + m.num;
      if (m.addr) popup += '<br/>' + m.addr;
      if (m.lastVal != null) popup += '<br/>Last: ' + parseFloat(m.lastVal).toFixed(1) + ' m³';
      L.marker([lat, lng], { icon: icon })
        .addTo(map)
        .bindPopup(popup);
      bounds.push([lat, lng]);
    }

    if (bounds.length > 0) {
      map.fitBounds(bounds, { padding: [30, 30] });
    } else {
      map.setView([13.94, 121.63], 13);
    }
  </script>
</body>
</html>`;
}

export default function MapScreen() {
  const navigation = useNavigation();
  const [customers, setCustomers] = useState<CustomerRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const data = await getCustomersWithCoordinates();
      setCustomers(data);
      setLoading(false);
    })();
  }, []);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Text style={styles.backText}>{'\u2190'} Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Map View</Text>
        <View style={styles.backBtn} />
      </View>

      {loading ? (
        <View style={styles.loading}>
          <ActivityIndicator size="large" color="#4A90D9" />
          <Text style={styles.loadingText}>Loading customers...</Text>
        </View>
      ) : customers.length === 0 ? (
        <View style={styles.loading}>
          <Text style={styles.emptyIcon}>{'\uD83D\uDDFA\uFE0F'}</Text>
          <Text style={styles.loadingText}>No customers with coordinates found</Text>
          <Text style={styles.emptyHint}>Sync customer data first</Text>
        </View>
      ) : (
        <WebView
          style={styles.map}
          source={{ html: buildMapHtml(customers) }}
          originWhitelist={['about:blank']}
          javaScriptEnabled
          domStorageEnabled
          startInLoadingState
          renderLoading={() => (
            <View style={styles.loading}>
              <ActivityIndicator size="large" color="#4A90D9" />
            </View>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F5F7FA',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingTop: 60,
    paddingBottom: 12,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#E8ECF0',
  },
  backBtn: {
    width: 70,
  },
  backText: {
    fontSize: 16,
    color: '#4A90D9',
    fontWeight: '600',
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1A1A2E',
  },
  map: {
    flex: 1,
  },
  loading: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
  },
  loadingText: {
    fontSize: 15,
    color: '#666',
  },
  emptyIcon: {
    fontSize: 48,
  },
  emptyHint: {
    fontSize: 13,
    color: '#999',
  },
});
