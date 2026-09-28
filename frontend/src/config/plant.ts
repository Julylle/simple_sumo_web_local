// Plant overview only. Reactor coordinates require confirmation from the site.
export const plant = {
  name: "Subiaco Water Resource Recovery Facility",
  address: "Lemnos Street, Shenton Park, Western Australia",
  latitude: -31.95524,
  longitude: 115.7937,
  addressSource: "https://der.wa.gov.au/component/k2/item/17576-l4726-1991-16",
  locationSource: "https://mapcarta.com/W48364152",
};

export interface ReactorLocation {
  id: string;
  label: string;
  latitude: number;
  longitude: number;
}

// Add only confirmed coordinates for the model's five reactor zones.
export const reactorLocations: ReactorLocation[] = [];

export function googleEarthUrl(latitude: number, longitude: number) {
  return `https://earth.google.com/web/search/${latitude},${longitude}`;
}
