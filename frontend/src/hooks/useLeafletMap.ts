import { useEffect, useRef, useState } from "react"
import L from "leaflet"
import "leaflet/dist/leaflet.css"

/** Koyu tema harita katmanı. */
export function darkTiles() {
  return L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap &copy; CARTO",
    maxZoom: 18,
  })
}

/** Bir div içinde Leaflet haritası kurar ve örneği döndürür. */
export function useLeafletMap(center: [number, number], zoom: number) {
  const ref = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<L.Map | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!ref.current || mapRef.current) return
    const map = L.map(ref.current, { preferCanvas: true, zoomControl: true }).setView(center, zoom)
    darkTiles().addTo(map)
    mapRef.current = map
    setReady(true)
    // Sekme geçişlerinde konteyner boyutu değiştiği için yeniden ölçtür
    const t = setTimeout(() => map.invalidateSize(), 120)
    return () => {
      clearTimeout(t)
      map.remove()
      mapRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { ref, map: mapRef, ready }
}

/** Fay hatlarını bir kez indirip önbellekte tutar. */
let faultCache: GeoJSON.FeatureCollection | null = null
export async function loadFaults(): Promise<GeoJSON.FeatureCollection | null> {
  if (faultCache) return faultCache
  try {
    const res = await fetch("/api/faults")
    if (!res.ok) return null
    faultCache = await res.json()
    return faultCache
  } catch {
    return null
  }
}

export const faultStyle: L.PathOptions = {
  color: "#f43f5e",
  weight: 1.1,
  opacity: 0.45,
}
