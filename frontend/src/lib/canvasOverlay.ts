import L from "leaflet";

/**
 * An L.ImageOverlay whose "image" is a <canvas>. Leaflet handles positioning
 * and zoom animation exactly as for images; we just repaint the canvas in
 * place, so changing frames never reloads anything or flickers.
 */
const CanvasOverlayClass = L.ImageOverlay.extend({
  _initImage(this: L.ImageOverlay & { _image: HTMLCanvasElement; _url: unknown; _zoomAnimated: boolean }) {
    const el = (this._image = this._url as HTMLCanvasElement);
    L.DomUtil.addClass(el, "leaflet-image-layer");
    if (this._zoomAnimated) L.DomUtil.addClass(el, "leaflet-zoom-animated");
    if (this.options.className) L.DomUtil.addClass(el, this.options.className);
    el.onselectstart = L.Util.falseFn as () => boolean;
    el.onmousemove = L.Util.falseFn as () => boolean;
  },
});

export function canvasOverlay(
  canvas: HTMLCanvasElement,
  bounds: L.LatLngBoundsExpression,
  options: L.ImageOverlayOptions,
): L.ImageOverlay {
  // The canvas stands in for the image URL; _initImage above picks it up.
  return new (CanvasOverlayClass as unknown as new (
    c: HTMLCanvasElement,
    b: L.LatLngBoundsExpression,
    o: L.ImageOverlayOptions,
  ) => L.ImageOverlay)(canvas, bounds, options);
}
