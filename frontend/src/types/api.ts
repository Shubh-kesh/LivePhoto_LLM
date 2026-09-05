/** Compile-time helper types not backed by a runtime schema. */

export type JsonRecord = Record<string, unknown>

export type JsonValue = string | number | boolean | null | JsonValue[] | JsonRecord
