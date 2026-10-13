// types.d.ts — ambient declarations: a `.wasm` imported `with { type: "file" }` is a path string under Bun.
declare module "*.wasm" {
  const path: string;
  export default path;
}
