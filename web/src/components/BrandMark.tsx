/** The Super Teacher app icon. Served from /brand (copied from brand/logo by brand/tools/export_png.mjs); decorative, the name sits beside it. */
export default function BrandMark({ size = 30 }: { size?: number }) {
  return <img className="brand-mark" src="/brand/app-icon.svg" alt="" width={size} height={size} />;
}
