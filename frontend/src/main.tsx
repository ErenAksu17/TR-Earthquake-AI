import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import {
  BarController, BarElement, CategoryScale, Chart as ChartJS, Filler, Legend,
  LinearScale, LineController, LineElement, LogarithmicScale, PointElement,
  ScatterController, Title, Tooltip,
} from "chart.js"
import "./index.css"
import App from "./App.tsx"

// Modüler Chart.js'te hem elemanlar HEM controller'lar kaydedilmeli
ChartJS.register(
  CategoryScale, LinearScale, LogarithmicScale,
  BarController, LineController, ScatterController,
  BarElement, PointElement, LineElement, Filler,
  Title, Tooltip, Legend,
)

// Koyu tema varsayılan
document.documentElement.classList.add("dark")

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
