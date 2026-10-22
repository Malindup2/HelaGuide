/**
 * Test-only access to the backend's captured responses (docs/examples/frontend-api-2026-10-22).
 * The application never imports these; they exist so tests exercise the real response shape.
 */
import birth from '../../../../docs/examples/frontend-api-2026-10-22/standard-official-birth_copy-v3.json';
import nic from '../../../../docs/examples/frontend-api-2026-10-22/standard-official-nic_amendment-v3.json';
import company from '../../../../docs/examples/frontend-api-2026-10-22/standard-official-company_pack-v3.json';
import practiceStandard from '../../../../docs/examples/frontend-api-2026-10-22/standard-synthetic-practice-v2.json';
import practicePreview from '../../../../docs/examples/frontend-api-2026-10-22/preview-synthetic-practice-v2.json';
import practiceRecap from '../../../../docs/examples/frontend-api-2026-10-22/practice-earned-recap.json';
import procedures from '../../../../docs/examples/frontend-api-2026-10-22/procedures.json';
import status from '../../../../docs/examples/frontend-api-2026-10-22/status.json';
import type { GuidanceResponse, ProcedureInfo, ApiStatus } from '../types';

const clone = <T,>(v: unknown) => structuredClone(v) as T;
export const birthStandard = () => clone<GuidanceResponse>(birth.response);
export const nicStandard = () => clone<GuidanceResponse>(nic.response);
export const companyStandard = () => clone<GuidanceResponse>(company.response);
export const practiceStd = () => clone<GuidanceResponse>(practiceStandard.response);
export const practiceRich = () => clone<GuidanceResponse>(practicePreview.response);
export const practiceWithRecap = () => clone<GuidanceResponse>(practiceRecap.response);
export const procedureList = () => clone<ProcedureInfo[]>(procedures.response);
export const apiStatus = () => clone<ApiStatus>(status.response);
import v31Std from '../../../../docs/examples/frontend-api-3.1-2026-10-22/standard-synthetic-practice-v2.json';
import v31Nic from '../../../../docs/examples/frontend-api-3.1-2026-10-22/standard-official-nic_amendment-v3.json';
import v31ConciseOff from '../../../../docs/examples/frontend-api-3.1-2026-10-22/preview-concise-off.json';
import v31ConciseOn from '../../../../docs/examples/frontend-api-3.1-2026-10-22/preview-concise-on.json';
import v31DetailedOff from '../../../../docs/examples/frontend-api-3.1-2026-10-22/preview-detailed-off.json';
import v31DetailedOn from '../../../../docs/examples/frontend-api-3.1-2026-10-22/preview-detailed-on.json';
import v31RichJson from '../../../../docs/examples/frontend-api-3.1-2026-10-22/preview-rich.json';
import v31Parallel from '../../../../docs/examples/frontend-api-3.1-2026-10-22/preview-parallel-guided.json';
import af0 from '../../../../docs/examples/frontend-api-3.1-actionfacts-2026-10-22/standard-synthetic-practice-v2.json';
import af1 from '../../../../docs/examples/frontend-api-3.1-actionfacts-2026-10-22/standard-official-nic_amendment-v3.json';
import af2 from '../../../../docs/examples/frontend-api-3.1-actionfacts-2026-10-22/standard-official-birth_copy-v3.json';
import af3 from '../../../../docs/examples/frontend-api-3.1-actionfacts-2026-10-22/standard-synthetic-parallel-v1.json';
import af4 from '../../../../docs/examples/frontend-api-3.1-actionfacts-2026-10-22/preview-concise-off.json';
import af5 from '../../../../docs/examples/frontend-api-3.1-actionfacts-2026-10-22/preview-concise-on.json';
import af6 from '../../../../docs/examples/frontend-api-3.1-actionfacts-2026-10-22/preview-detailed-off.json';
import af7 from '../../../../docs/examples/frontend-api-3.1-actionfacts-2026-10-22/preview-detailed-on.json';
import af8 from '../../../../docs/examples/frontend-api-3.1-actionfacts-2026-10-22/preview-rich.json';
import af9 from '../../../../docs/examples/frontend-api-3.1-actionfacts-2026-10-22/preview-parallel-guided.json';
import guest from '../../../../docs/examples/frontend-api-2026-10-22/guest.json';
export const guestSession = () => clone<unknown>(guest.response);
// Content 3.1: real responses captured from the isolated 3.1 runtime (research/export_guidance_v31_examples.py).
export const v31Standard = () => clone<GuidanceResponse>(v31Std.response);
export const v31NicFallback = () => clone<GuidanceResponse>(v31Nic.response);
export const v31Combo = (explanation: 'concise' | 'detailed', disclosure: 'off' | 'on') =>
  clone<GuidanceResponse>({ 'concise/off': v31ConciseOff, 'concise/on': v31ConciseOn, 'detailed/off': v31DetailedOff, 'detailed/on': v31DetailedOn }[`${explanation}/${disclosure}`].response);
export const v31Rich = () => clone<GuidanceResponse>(v31RichJson.response);
export const v31ParallelGuided = () => clone<GuidanceResponse>(v31Parallel.response);

// Action-scoped facts: real 3.1 responses after the reviewed destinations and documents were added (docs/examples/frontend-api-3.1-actionfacts-2026-10-22).
const afTable = { 'standard-synthetic-practice-v2': af0, 'standard-official-nic_amendment-v3': af1, 'standard-official-birth_copy-v3': af2, 'standard-synthetic-parallel-v1': af3, 'preview-concise-off': af4, 'preview-concise-on': af5, 'preview-detailed-off': af6, 'preview-detailed-on': af7, 'preview-rich': af8, 'preview-parallel-guided': af9 };
export const actionFacts = (name: keyof typeof afTable) => clone<GuidanceResponse>(afTable[name].response);
