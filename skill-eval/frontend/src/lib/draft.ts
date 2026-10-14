import type { Json } from "./api";

export function draftDefaults(data: Json = {}): Json {
  return {
    name: "",
    project_path: "",
    skill_path: "",
    requirement: "",
    dimensions: [],
    packages: {},
    generator_provider: "chrys",
    generator_model: "",
    ...data,
    setup: { commands: [], timeout_seconds: 900, ...data.setup },
  };
}
