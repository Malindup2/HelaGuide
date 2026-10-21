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
import guest from '../../../../docs/examples/frontend-api-2026-10-22/guest.json';
export const guestSession = () => clone<unknown>(guest.response);
