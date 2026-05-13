import { Route, Routes } from "react-router-dom";
import { Navbar } from "../components/layout/Navbar";
import { ProtectedRoute } from "../components/common/ProtectedRoute";
import { HomePage } from "../pages/HomePage";
import { LoginPage } from "../pages/LoginPage";
import { PlacesPage } from "../pages/PlacesPage";
import { TripPlanPage } from "../pages/TripPlanPage";
import { AccommodationSearchPage } from "../pages/AccommodationSearchPage";
import { FlightSearchPage } from "../pages/FlightSearchPage";
import { BudgetPage } from "../pages/BudgetPage";
import { DiaryPage } from "../pages/DiaryPage";
import { WeatherPage } from "../pages/WeatherPage";

export function AppRoutes() {
  return (
    <>
      <Navbar />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/places" element={<PlacesPage />} />
        <Route path="/weather" element={<WeatherPage />} />
        <Route element={<ProtectedRoute />}>
          <Route path="/trip-plan" element={<TripPlanPage />} />
          <Route path="/trips/:tripId" element={<TripPlanPage />} />
          <Route path="/accommodations" element={<AccommodationSearchPage />} />
          <Route path="/flights" element={<FlightSearchPage />} />
          <Route path="/budget" element={<BudgetPage />} />
          <Route path="/diary" element={<DiaryPage />} />
        </Route>
      </Routes>
    </>
  );
}
