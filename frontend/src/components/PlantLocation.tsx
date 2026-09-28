import { useState } from "react";
import { googleEarthUrl, plant, reactorLocations } from "../config/plant";

export function PlantLocation() {
  const [selectedId, setSelectedId] = useState("plant");
  const selected = reactorLocations.find((reactor) => reactor.id === selectedId);
  const { latitude, longitude } = selected ?? plant;
  const label = selected?.label ?? plant.name;
  const mapUrl = `https://maps.google.com/maps?q=${latitude},${longitude}&t=k&z=${selected ? 20 : 17}&output=embed`;

  return (
    <section className="plant-location" aria-labelledby="plant-location-title">
      <div className="plant-location-header">
        <div>
          <h2 id="plant-location-title">Plant location</h2>
          <p>{plant.name}</p>
          <address>{plant.address}</address>
        </div>
        <a className="secondary" href={googleEarthUrl(latitude, longitude)} target="_blank" rel="noopener noreferrer">
          Open in Google Earth
        </a>
      </div>
      <div className="plant-location-content">
        <iframe
          key={selectedId}
          title={`Google Maps satellite view: ${label}`}
          src={mapUrl}
          loading="lazy"
          allowFullScreen
          referrerPolicy="no-referrer-when-downgrade"
        />
        <aside className="plant-reactors" aria-label="Reactor locations">
          <h3>Reactor locations</h3>
          <button type="button" aria-pressed={selectedId === "plant"} onClick={() => setSelectedId("plant")}>
            Plant overview
          </button>
          {reactorLocations.map((reactor) => (
            <button type="button" key={reactor.id} aria-pressed={selectedId === reactor.id} onClick={() => setSelectedId(reactor.id)}>
              {reactor.label}
            </button>
          ))}
          {reactorLocations.length === 0 && (
            <p>The locations of model reactors 1–5 are awaiting confirmation.</p>
          )}
          <p>Satellite view: Google Maps. Open Google Earth for the Earth view.</p>
          <a href={plant.addressSource} target="_blank" rel="noopener noreferrer">Facility address source</a>
          <a href={plant.locationSource} target="_blank" rel="noopener noreferrer">Plant overview location source</a>
        </aside>
      </div>
    </section>
  );
}
