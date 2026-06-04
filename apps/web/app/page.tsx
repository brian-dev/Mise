import { MEAL_TYPES, type MealType } from "@mise/shared";

export default function Home() {
  return (
    <main style={{ fontFamily: "system-ui", padding: "2rem", maxWidth: 640 }}>
      <h1>Mise</h1>
      <p>AI meal planning — plan, shop, cook, repeat.</p>
      <p>Meal types from the shared package:</p>
      <ul>
        {MEAL_TYPES.map((m: MealType) => (
          <li key={m}>{m}</li>
        ))}
      </ul>
    </main>
  );
}
