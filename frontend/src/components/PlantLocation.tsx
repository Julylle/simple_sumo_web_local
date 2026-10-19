import { t, useLanguage } from '../i18n';
import { useState } from "react";
import { googleEarthUrl, plant, reactorLocations } from "../config/plant";

export function PlantLocation() {
  useLanguage();
  const [selectedId, setSelectedId] = useState("plant");
  const selected = reactorLocations.find((reactor) => reactor.id === selectedId);
  const { latitude, longitude } = selected ?? plant;
  const label = selected?.label ?? plant.name;
  const mapUrl = `https://maps.google.com/maps?q=${latitude},${longitude}&t=k&z=${selected ? 20 : 17}&output=embed`;

  return (
    <section className="plant-location" aria-labelledby="plant-location-title">
      <div className="plant-location-header">
        <div>
          <h2 id="plant-location-title">{t("Plant location")}</h2>
          <p>{t(plant.name)}</p>
          <address>{t(plant.address)}</address>
        </div>
        <a className="secondary" href={googleEarthUrl(latitude, longitude)} target="_blank" rel="noopener noreferrer"> {t("Open in Google Earth")} </a>
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
        <aside className="plant-reactors" aria-label={t("Reactor locations")}>
          <h3>{t("Reactor locations")}</h3>
          <button type="button" aria-pressed={selectedId === "plant"} onClick={() => setSelectedId("plant")}> {t("Plant overview")} </button>
          {reactorLocations.map((reactor) => (
            <button type="button" key={reactor.id} aria-pressed={selectedId === reactor.id} onClick={() => setSelectedId(reactor.id)}>
              {t(reactor.label)}
            </button>
          ))}
          {reactorLocations.length === 0 && (
            <p>{t("The locations of model reactors 1–5 are awaiting confirmation.")}</p>
          )}
          <p>{t("Satellite view: Google Maps. Open Google Earth for the Earth view.")}</p>
          <a href={plant.addressSource} target="_blank" rel="noopener noreferrer">{t("Facility address source")}</a>
        </aside>
      </div>
    </section>
  );
}
