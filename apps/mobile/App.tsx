import { StatusBar } from "expo-status-bar";
import { StyleSheet, Text, View } from "react-native";

import { MEAL_TYPES } from "@mise/shared";

export default function App() {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Mise</Text>
      <Text>AI meal planning — plan, shop, cook, repeat.</Text>
      <Text style={styles.subtle}>Meal types: {MEAL_TYPES.join(", ")}</Text>
      <StatusBar style="auto" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#fff",
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    gap: 8,
  },
  title: { fontSize: 28, fontWeight: "600" },
  subtle: { color: "#666" },
});
