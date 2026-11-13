import { useMemo, useRef, useState } from 'react';
import {
  useCreateMapMarker,
  useCreateMapRegion,
  useCreateTimelineEvent,
  useCreateUniverseCalendar,
  useCreateCalendarEra,
  useCreateUniverseMap,
  useDeleteMapMarker,
  useDeleteMapRegion,
  useDeleteTimelineEvent,
  useListCalendarEras,
  useListMapMarkers,
  useListMapRegions,
  useListTimelineEvents,
  useListUniverseCalendars,
  useListUniverseMaps,
  useUploadUniverseAsset,
  useUpdateMapMarker,
  type MapMarkerResponse,
  type MapRegionResponse,
  type TimelineEventResponse,
} from '@workspace/api-client-react';
import { CalendarDays, MapPin, Minus, Plus, RefreshCw, Trash2, Upload } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';

type Props = { universeId: string; canEdit: boolean; initialView?: 'atlas' | 'chronos' };
type Point = { x: number; y: number };

const panel = 'border border-[#d9d1c2] bg-[#faf7ef] p-5';
const field = 'rounded border border-[#d5cebf] bg-white px-3 py-2 text-xs text-[#253a32] focus:border-[#9b4a36] focus:outline-none';
const primary = 'inline-flex items-center gap-2 rounded bg-[#294238] px-3 py-2 text-xs font-semibold text-[#f7f2e7] hover:bg-[#38574a] disabled:opacity-50';
const secondary = 'inline-flex items-center gap-2 rounded border border-[#c9c1b2] px-3 py-2 text-xs font-semibold text-[#53655b] hover:border-[#9b4a36]';

function message(error: unknown, fallback: string) {
  const value = error as { data?: { error?: { message?: string } }; message?: string };
  return value?.data?.error?.message || value?.message || fallback;
}

function AtlasPanel({ universeId, canEdit }: Props) {
  const queryClient = useQueryClient();
  const [selectedMapId, setSelectedMapId] = useState('');
  const [mapTitle, setMapTitle] = useState('');
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const panStart = useRef<{ pointerId: number; x: number; y: number; baseX: number; baseY: number } | null>(null);
  const markerDrag = useRef<{ markerId: string; pointerId: number; startX: number; startY: number; point: Point } | null>(null);
  const [dragPoint, setDragPoint] = useState<{ markerId: string; point: Point } | null>(null);
  const [notice, setNotice] = useState('');
  const [drawingRegion, setDrawingRegion] = useState(false);
  const [regionPoints, setRegionPoints] = useState<Point[]>([]);
  const mapsQuery = useListUniverseMaps(universeId, { limit: 200, offset: 0 });
  const maps = mapsQuery.data?.items ?? [];
  const selectedMap = maps.find((map) => map.id === selectedMapId) ?? maps[0];
  const mapId = selectedMap?.id ?? '';
  const markerQuery = useListMapMarkers(universeId, mapId, { query: { enabled: Boolean(mapId) } });
  const regionQuery = useListMapRegions(universeId, mapId, { query: { enabled: Boolean(mapId) } });
  const markers = markerQuery.data?.items ?? [];
  const regions = regionQuery.data?.items ?? [];
  const createMap = useCreateUniverseMap();
  const uploadAsset = useUploadUniverseAsset();
  const createMarker = useCreateMapMarker();
  const updateMarker = useUpdateMapMarker();
  const deleteMarker = useDeleteMapMarker();
  const createRegion = useCreateMapRegion();
  const deleteRegion = useDeleteMapRegion();
  const refresh = async () => queryClient.invalidateQueries();

  const pointFromEvent = (event: React.PointerEvent<HTMLDivElement>): Point => {
    const rect = event.currentTarget.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, ((event.clientX - rect.left - rect.width / 2 - pan.x) / zoom + rect.width / 2) / rect.width)),
      y: Math.max(0, Math.min(1, ((event.clientY - rect.top - rect.height / 2 - pan.y) / zoom + rect.height / 2) / rect.height)),
    };
  };

  const createNewMap = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const file = (new FormData(form).get('map-image') as File | null) ?? null;
    try {
      const asset = file?.size ? await uploadAsset.mutateAsync({ universeId, data: { file } }) : undefined;
      const map = await createMap.mutateAsync({
        universeId,
        data: { title: mapTitle.trim(), image_asset_id: asset?.id },
      });
      setSelectedMapId(map.id);
      setMapTitle('');
      form.reset();
      setNotice('Map created. Click its canvas to place a marker.');
      await refresh();
    } catch (error) {
      setNotice(message(error, 'Could not create this map.'));
    }
  };

  const onCanvasClick = async (event: React.PointerEvent<HTMLDivElement>) => {
    if (!canEdit || event.button !== 0 || event.target !== event.currentTarget) return;
    const point = pointFromEvent(event);
    if (drawingRegion) {
      setRegionPoints((current) => [...current, point]);
      return;
    }
    const title = window.prompt('Name this place:');
    if (!title?.trim()) return;
    try {
      await createMarker.mutateAsync({
        universeId,
        mapId,
        data: { title: title.trim(), x_norm: point.x, y_norm: point.y, marker_type: 'poi' },
      });
      setNotice('Marker placed. Its normalized position is preserved across viewport sizes.');
      await refresh();
    } catch (error) {
      setNotice(message(error, 'Could not place the marker.'));
    }
  };

  const saveRegion = async () => {
    const title = window.prompt('Name this region:');
    if (!title?.trim() || regionPoints.length < 3) return;
    try {
      await createRegion.mutateAsync({
        universeId,
        mapId,
        data: { title: title.trim(), geometry_json: { type: 'polygon', points: regionPoints } },
      });
      setRegionPoints([]);
      setDrawingRegion(false);
      setNotice('Region saved.');
      await refresh();
    } catch (error) {
      setNotice(message(error, 'Could not save the region.'));
    }
  };

  const background = selectedMap?.image_asset_id
    ? `/api/v1/assets/${selectedMap.image_asset_id}`
    : undefined;

  return (
    <section className="space-y-5" data-testid="panel-atlas">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="ww-kicker text-[#9b4a36]">Atlas / Field maps</p>
          <h2 className="ww-display mt-1 text-3xl text-[#263b32]">Places take shape</h2>
        </div>
        <button type="button" className={secondary} onClick={() => void refresh()} aria-label="Refresh maps"><RefreshCw size={14} /> Refresh</button>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_270px]">
        <div className={panel}>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <label className="sr-only" htmlFor="atlas-map-select">Choose map</label>
            <select id="atlas-map-select" className={field} value={selectedMap?.id ?? ''} onChange={(event) => { setSelectedMapId(event.target.value); setRegionPoints([]); }}>
              {maps.length === 0 && <option value="">No maps yet</option>}
              {maps.map((map) => <option key={map.id} value={map.id}>{map.title}</option>)}
            </select>
            {selectedMap && (
              <div className="flex items-center gap-2">
                <button type="button" className={secondary} onClick={() => setZoom((value) => Math.max(1, +(value - 0.25).toFixed(2)))} aria-label="Zoom out"><Minus size={14} /></button>
                <span className="min-w-12 text-center text-xs text-[#53655b]">{Math.round(zoom * 100)}%</span>
                <button type="button" className={secondary} onClick={() => setZoom((value) => Math.min(2.5, +(value + 0.25).toFixed(2)))} aria-label="Zoom in"><Plus size={14} /></button>
              </div>
            )}
          </div>

          {selectedMap ? (
            <>
              <div
                className={`relative aspect-[16/9] touch-none overflow-hidden border border-[#c9c1b2] bg-[#e9e3d6] ${canEdit ? 'cursor-crosshair' : ''}`}
                role="application"
                aria-label={`Map canvas: ${selectedMap.title}. ${canEdit ? 'Click to add a marker. Alt-drag to pan.' : 'Read only.'}`}
                onPointerDown={(event) => {
                  if ((event.button === 1 || (event.button === 0 && event.altKey)) && zoom > 1) {
                    event.preventDefault();
                    event.currentTarget.setPointerCapture(event.pointerId);
                    panStart.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, baseX: pan.x, baseY: pan.y };
                  } else if (event.isPrimary) {
                    void onCanvasClick(event);
                  }
                }}
                onPointerMove={(event) => {
                  const start = panStart.current;
                  if (start?.pointerId === event.pointerId) setPan({ x: start.baseX + event.clientX - start.x, y: start.baseY + event.clientY - start.y });
                  const dragging = markerDrag.current;
                  if (dragging?.pointerId === event.pointerId) setDragPoint({ markerId: dragging.markerId, point: pointFromEvent(event) });
                }}
                onPointerUp={(event) => {
                  if (panStart.current?.pointerId === event.pointerId) panStart.current = null;
                  const dragging = markerDrag.current;
                  if (dragging?.pointerId === event.pointerId) {
                    const endPoint = pointFromEvent(event);
                    markerDrag.current = null;
                    setDragPoint(null);
                    const marker = markers.find((item) => item.id === dragging.markerId);
                    if (marker && (Math.abs(endPoint.x - dragging.startX) > 0.002 || Math.abs(endPoint.y - dragging.startY) > 0.002)) {
                      void updateMarker.mutateAsync({ universeId, mapId, markerId: marker.id, data: { x_norm: endPoint.x, y_norm: endPoint.y, expected_version: marker.version } })
                        .then(async () => { setNotice(`${marker.title} moved.`); await refresh(); })
                        .catch((error) => setNotice(message(error, 'Could not move this marker.')));
                    }
                  }
                }}
                onPointerCancel={() => { panStart.current = null; markerDrag.current = null; setDragPoint(null); }}
                onWheel={(event) => { if (event.ctrlKey || event.metaKey) { event.preventDefault(); setZoom((value) => Math.max(1, Math.min(2.5, +(value + (event.deltaY < 0 ? 0.1 : -0.1)).toFixed(2)))); } }}
                data-testid="atlas-map-canvas"
              >
                <div className="pointer-events-none absolute inset-0 origin-center transition-transform duration-150" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}>
                  {background ? <img src={background} alt={`Background for ${selectedMap.title}`} className="absolute inset-0 h-full w-full select-none object-fill" draggable={false} /> : (
                    <div className="absolute inset-0 opacity-35" style={{ backgroundImage: 'linear-gradient(#948d7f 1px, transparent 1px), linear-gradient(90deg, #948d7f 1px, transparent 1px)', backgroundSize: '8% 8%' }} />
                  )}
                  <svg className="absolute inset-0 h-full w-full overflow-visible" viewBox="0 0 1000 562.5" preserveAspectRatio="none" aria-label="Map regions">
                    {regions.map((region: MapRegionResponse) => {
                      const points = (region.geometry_json as { points?: Point[] }).points ?? [];
                      return <polygon key={region.id} points={points.map((point) => `${point.x * 1000},${point.y * 562.5}`).join(' ')} fill="rgba(100,133,107,.25)" stroke="#456a50" strokeWidth="2" vectorEffect="non-scaling-stroke" />;
                    })}
                    {regionPoints.length > 0 && <polyline points={regionPoints.map((point) => `${point.x * 1000},${point.y * 562.5}`).join(' ')} fill="rgba(164,82,59,.18)" stroke="#9b4a36" strokeWidth="2" vectorEffect="non-scaling-stroke" />}
                  </svg>
                    {markers.map((marker: MapMarkerResponse) => (
                    <button
                      key={marker.id}
                      type="button"
                      title={`${marker.title}${marker.description ? ` — ${marker.description}` : ''}`}
                      aria-label={`Map marker ${marker.title}`}
                      className="pointer-events-auto absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[#f7f2e7] bg-[#9b4a36] p-1 text-white shadow hover:scale-125 focus:outline focus:outline-2 focus:outline-offset-2 focus:outline-[#294238]"
                      style={{ left: `${(dragPoint?.markerId === marker.id ? dragPoint.point.x : marker.x_norm) * 100}%`, top: `${(dragPoint?.markerId === marker.id ? dragPoint.point.y : marker.y_norm) * 100}%` }}
                      onPointerDown={(event) => {
                        event.stopPropagation();
                        if (!canEdit || event.button !== 0) return;
                        event.currentTarget.closest('[data-testid="atlas-map-canvas"]')?.setPointerCapture(event.pointerId);
                        markerDrag.current = { markerId: marker.id, pointerId: event.pointerId, startX: marker.x_norm, startY: marker.y_norm, point: { x: marker.x_norm, y: marker.y_norm } };
                      }}
                      onClick={async (event) => {
                        event.stopPropagation();
                        if (!canEdit) { setNotice(`${marker.title} · ${Math.round(marker.x_norm * 100)}%, ${Math.round(marker.y_norm * 100)}%`); return; }
                        const title = window.prompt('Edit marker name:', marker.title);
                        if (!title?.trim() || title.trim() === marker.title) return;
                        try {
                          await updateMarker.mutateAsync({ universeId, mapId, markerId: marker.id, data: { title: title.trim(), expected_version: marker.version } });
                          setNotice('Marker updated.');
                          await refresh();
                        } catch (error) { setNotice(message(error, 'Could not update this marker.')); }
                      }}
                    ><MapPin size={13} /></button>
                  ))}
                </div>
                {!background && <p className="pointer-events-none absolute bottom-3 left-3 bg-[#faf7ef]/90 px-2 py-1 text-[10px] text-[#53655b]">Normalized canvas · {selectedMap.width} × {selectedMap.height}</p>}
                {drawingRegion && <p className="pointer-events-none absolute right-3 top-3 bg-[#faf7ef]/90 px-2 py-1 text-[10px] text-[#9b4a36]">Click at least 3 corners to draw a region ({regionPoints.length} points)</p>}
              </div>
              {canEdit && drawingRegion && (
                <div className="mt-3 flex gap-2">
                  <button type="button" className={primary} disabled={regionPoints.length < 3 || createRegion.isPending} onClick={() => void saveRegion()}>Save region ({regionPoints.length} points)</button>
                  <button type="button" className={secondary} onClick={() => { setRegionPoints([]); setDrawingRegion(false); }}>Cancel</button>
                </div>
              )}
            </>
          ) : (
            <div className="flex aspect-[16/9] flex-col items-center justify-center border border-dashed border-[#c9c1b2] text-center">
              <MapPin size={28} className="text-[#9b4a36]" />
              <p className="ww-display mt-3 text-2xl text-[#30463b]">An atlas begins with a blank leaf.</p>
              <p className="mt-1 text-xs text-[#788078]">Create a map, then add places and drawn regions.</p>
            </div>
          )}
          {notice && <p role="status" aria-live="polite" className="mt-3 text-xs text-[#53655b]">{notice}</p>}
        </div>

        <aside className="space-y-4">
          {canEdit && (
            <form onSubmit={(event) => void createNewMap(event)} className={`${panel} space-y-3`}>
              <h3 className="font-serif text-lg text-[#253a32]">New map</h3>
              <label className="block text-[11px] font-semibold text-[#53655b]" htmlFor="atlas-map-title">Map name</label>
              <input id="atlas-map-title" className={`${field} w-full`} required maxLength={150} value={mapTitle} onChange={(event) => setMapTitle(event.target.value)} placeholder="The Shattered Coast" />
              <label className="flex cursor-pointer items-center gap-2 text-xs text-[#53655b]">
                <Upload size={14} /> Add background image
                <input className="sr-only" type="file" name="map-image" accept="image/png,image/jpeg,image/webp" />
              </label>
              <button className={primary} type="submit" disabled={createMap.isPending || uploadAsset.isPending}>{createMap.isPending || uploadAsset.isPending ? 'Creating…' : 'Create map'}</button>
            </form>
          )}
          {selectedMap && (
            <div className={panel}>
              <div className="flex items-center justify-between">
                <h3 className="font-serif text-lg text-[#253a32]">Overlays</h3>
                {canEdit && <button type="button" className={secondary} onClick={() => { setDrawingRegion(true); setRegionPoints([]); }}>Draw region</button>}
              </div>
              <p className="mt-1 text-[10px] leading-4 text-[#788078]">Click the canvas to place normalized-coordinate markers. Zoom never changes stored locations.</p>
              <ul className="mt-4 space-y-2">
                {markers.map((marker: MapMarkerResponse) => <li key={marker.id} className="flex items-center justify-between gap-2 border-t border-[#ded7ca] pt-2 text-xs"><span className="min-w-0 truncate text-[#34473d]">{marker.title}</span>{canEdit && <button type="button" aria-label={`Delete marker ${marker.title}`} className="text-[#9b4a36]" onClick={async () => { if (window.confirm(`Delete marker “${marker.title}”?`)) { await deleteMarker.mutateAsync({ universeId, mapId, markerId: marker.id }); await refresh(); } }}><Trash2 size={13} /></button>}</li>)}
                {regions.map((region: MapRegionResponse) => <li key={region.id} className="flex items-center justify-between gap-2 border-t border-[#ded7ca] pt-2 text-xs"><span className="min-w-0 truncate text-[#53655b]">{region.title} · region</span>{canEdit && <button type="button" aria-label={`Delete region ${region.title}`} className="text-[#9b4a36]" onClick={async () => { if (window.confirm(`Delete region “${region.title}”?`)) { await deleteRegion.mutateAsync({ universeId, mapId, regionId: region.id }); await refresh(); } }}><Trash2 size={13} /></button>}</li>)}
                {markers.length + regions.length === 0 && <li className="border-t border-[#ded7ca] pt-3 text-xs text-[#899087]">No map overlays yet.</li>}
              </ul>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}

function ChronosPanel({ universeId, canEdit }: Props) {
  const queryClient = useQueryClient();
  const [calendarId, setCalendarId] = useState('');
  const [calendarName, setCalendarName] = useState('');
  const [monthDefinition, setMonthDefinition] = useState('Seed:30, Bloom:30, Harvest:30, Frost:30');
  const [leapCycle, setLeapCycle] = useState('');
  const [leapMonth, setLeapMonth] = useState('2');
  const [eraName, setEraName] = useState('');
  const [eraYear, setEraYear] = useState('0');
  const [eventTitle, setEventTitle] = useState('');
  const [year, setYear] = useState('1');
  const [month, setMonth] = useState('1');
  const [day, setDay] = useState('1');
  const [precision, setPrecision] = useState<'day' | 'month' | 'year' | 'range' | 'approximate'>('day');
  const [endYear, setEndYear] = useState('1');
  const [endMonth, setEndMonth] = useState('1');
  const [endDay, setEndDay] = useState('1');
  const [uncertainty, setUncertainty] = useState('10');
  const [search, setSearch] = useState('');
  const [notice, setNotice] = useState('');
  const calendarsQuery = useListUniverseCalendars(universeId, { limit: 200, offset: 0 });
  const calendars = calendarsQuery.data?.items ?? [];
  const selectedCalendar = calendars.find((calendar) => calendar.id === calendarId) ?? calendars[0];
  const activeCalendarId = selectedCalendar?.id ?? '';
  const erasQuery = useListCalendarEras(universeId, activeCalendarId, { query: { enabled: Boolean(activeCalendarId) } });
  const eventsQuery = useListTimelineEvents(universeId, { calendar_id: activeCalendarId || undefined, q: search || undefined, limit: 500, offset: 0 }, { query: { enabled: Boolean(activeCalendarId) } });
  const events = eventsQuery.data?.items ?? [];
  const eras = erasQuery.data?.items ?? [];
  const createCalendar = useCreateUniverseCalendar();
  const createEra = useCreateCalendarEra();
  const createEvent = useCreateTimelineEvent();
  const deleteEvent = useDeleteTimelineEvent();

  const scale = useMemo(() => {
    if (!events.length) return { min: 0, max: 1 };
    const min = Math.min(...events.map((event: TimelineEventResponse) => event.start_day_index));
    const max = Math.max(...events.map((event: TimelineEventResponse) => event.end_day_index ?? event.start_day_index));
    return { min, max: Math.max(min + 1, max) };
  }, [events]);
  const config = selectedCalendar?.config_json as { months?: Array<{ name: string; days: number }>; leap_rules?: Array<{ every_years: number; year_offset?: number; month: number; extra_days?: number }> } | undefined;
  const monthOptions = config?.months ?? [];
  const descriptionDate = (event: TimelineEventResponse) => {
    const date = event.start_date_json as { year: number; month?: number; day?: number };
    const monthName = date.month ? monthOptions[date.month - 1]?.name ?? `Month ${date.month}` : '';
    return [date.day != null ? `Day ${date.day}` : '', monthName, `Year ${date.year}`].filter(Boolean).join(' · ');
  };
  const refresh = async () => queryClient.invalidateQueries();

  const submitCalendar = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      const months = monthDefinition.split(',').map((entry) => {
        const [name, days] = entry.split(':').map((value) => value.trim());
        return { name, days: Number(days) };
      });
      const invalid = months.some((item) => !item.name || !Number.isInteger(item.days) || item.days < 1);
      if (invalid) throw new Error('Use month names and positive day counts, for example: Seed:30, Frost:28');
      const calendar = await createCalendar.mutateAsync({
        universeId,
        data: {
          name: calendarName.trim(),
          config_json: {
            months,
            weekdays: ['First', 'Second', 'Third', 'Fourth', 'Fifth', 'Sixth', 'Seventh'],
            epoch_offset: 0,
            leap_rules: leapCycle ? [{ every_years: Number(leapCycle), year_offset: 0, month: Number(leapMonth), extra_days: 1 }] : [],
          },
        },
      });
      setCalendarId(calendar.id);
      setCalendarName('');
      setNotice('Custom calendar created. Calendar rules become immutable once events exist.');
      await refresh();
    } catch (error) {
      setNotice(message(error, 'Could not create this calendar.'));
    }
  };

  const submitEvent = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedCalendar) return;
    try {
      const eventDate: { year: number; month?: number; day?: number } = { year: Number(year) };
      if (precision !== 'year') eventDate.month = Number(month);
      if (precision === 'day' || precision === 'approximate' || precision === 'range') eventDate.day = Number(day);
      const endDate = precision === 'range'
        ? { year: Number(endYear), month: Number(endMonth), day: Number(endDay) }
        : undefined;
      await createEvent.mutateAsync({
        universeId,
        data: {
          calendar_id: selectedCalendar.id,
          title: eventTitle.trim(),
          start_date_json: eventDate,
          date_precision: precision,
          end_date_json: endDate,
          uncertainty_json: precision === 'approximate' ? { before_days: Number(uncertainty), after_days: Number(uncertainty) } : undefined,
        },
      });
      setEventTitle('');
      setNotice('Timeline event recorded in this calendar.');
      await refresh();
    } catch (error) {
      setNotice(message(error, 'Could not save the event.'));
    }
  };

  return (
    <section className="space-y-5" data-testid="panel-chronos">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><p className="ww-kicker text-[#9b4a36]">Chronos / Calendars</p><h2 className="ww-display mt-1 text-3xl text-[#263b32]">Time has its own measure</h2></div>
        <label className="flex items-center gap-2 text-xs text-[#53655b]">
          Calendar
          <select className={field} value={selectedCalendar?.id ?? ''} onChange={(event) => setCalendarId(event.target.value)}>
            {calendars.length === 0 && <option value="">No calendars yet</option>}
            {calendars.map((calendar) => <option key={calendar.id} value={calendar.id}>{calendar.name}</option>)}
          </select>
        </label>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-5">
          {selectedCalendar ? (
            <div className={panel}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div><p className="ww-kicker text-[#899087]">{selectedCalendar.name}</p><h3 className="font-serif text-xl text-[#253a32]">Timeline</h3></div>
                <label className="sr-only" htmlFor="chronos-search">Filter events</label>
                <input id="chronos-search" className={field} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Filter events…" />
              </div>
              <div className="mt-5 space-y-3" data-testid="chronos-timeline">
                {events.map((item: TimelineEventResponse) => {
                  const end = item.end_day_index ?? item.start_day_index;
                  const left = ((item.start_day_index - scale.min) / (scale.max - scale.min)) * 90;
                  const width = Math.max(2, ((end - item.start_day_index + 1) / (scale.max - scale.min)) * 90);
                  return (
                    <article key={item.id} className="grid gap-2 border-t border-[#ded7ca] pt-3 sm:grid-cols-[145px_minmax(0,1fr)]" data-testid="timeline-event">
                      <div><p className="text-xs font-semibold text-[#34473d]">{item.title}</p><p className="mt-1 text-[10px] text-[#788078]">{descriptionDate(item)}{item.date_precision === 'approximate' ? ' · approximate' : item.date_precision === 'range' ? ' · range' : ''}</p></div>
                      <div className="relative h-8 rounded-sm bg-[#e9e3d6]" aria-label={`${item.title}: day ${item.start_day_index} to ${end}`}>
                        <div className="absolute top-1/2 h-3 min-w-2 -translate-y-1/2 rounded-full bg-[#64856b]" style={{ left: `${Math.min(96, left)}%`, width: `${Math.min(100 - Math.min(96, left), width)}%` }} />
                        {canEdit && <button type="button" aria-label={`Delete event ${item.title}`} className="absolute right-1 top-1 rounded p-1 text-[#9b4a36] hover:bg-white" onClick={async () => { if (window.confirm(`Delete “${item.title}”?`)) { await deleteEvent.mutateAsync({ universeId, eventId: item.id }); await refresh(); } }}><Trash2 size={12} /></button>}
                      </div>
                    </article>
                  );
                })}
                {events.length === 0 && <p className="py-6 text-center text-xs text-[#899087]">No timeline events match this view.</p>}
              </div>
              {eras.length > 0 && <div className="mt-5 border-t border-[#ded7ca] pt-4"><p className="ww-kicker mb-2 text-[#899087]">Eras</p><div className="flex flex-wrap gap-2">{eras.map((era) => <span key={era.id} className="rounded-full bg-[#294238]/10 px-3 py-1 text-[10px] text-[#294238]">{era.name}</span>)}</div></div>}
            </div>
          ) : (
            <div className={`${panel} flex min-h-60 flex-col items-center justify-center text-center`}><CalendarDays size={28} className="text-[#9b4a36]" /><p className="ww-display mt-3 text-2xl text-[#30463b]">Give history a calendar.</p><p className="mt-1 text-xs text-[#788078]">Define months and record events in your world's own time.</p></div>
          )}
          {notice && <p role="status" aria-live="polite" className="text-xs text-[#53655b]">{notice}</p>}
        </div>

        <aside className="space-y-4">
          {canEdit && (
            <form onSubmit={(event) => void submitCalendar(event)} className={`${panel} space-y-3`}>
              <h3 className="font-serif text-lg text-[#253a32]">New calendar</h3>
              <input className={`${field} w-full`} required maxLength={100} value={calendarName} onChange={(event) => setCalendarName(event.target.value)} placeholder="The Tide Reckoning" aria-label="Calendar name" />
                      <label className="block text-[10px] leading-4 text-[#788078]" htmlFor="chronos-months">Ordered months: name:days</label>
              <textarea id="chronos-months" className={`${field} w-full`} rows={3} value={monthDefinition} onChange={(event) => setMonthDefinition(event.target.value)} />
              <div className="grid grid-cols-[1fr_1fr] gap-2">
                <label className="text-[10px] text-[#788078]">Leap every years<input className={`${field} mt-1 w-full`} type="number" min={2} max={1000000} value={leapCycle} onChange={(event) => setLeapCycle(event.target.value)} placeholder="None" /></label>
                <label className="text-[10px] text-[#788078]">Extra day in month<input className={`${field} mt-1 w-full`} type="number" min={1} max={monthDefinition.split(',').length} value={leapMonth} onChange={(event) => setLeapMonth(event.target.value)} /></label>
              </div>
              <p className="text-[10px] leading-4 text-[#788078]">Calendar dates follow these rules only; no Gregorian assumptions.</p>
              <button className={primary} type="submit" disabled={createCalendar.isPending}>{createCalendar.isPending ? 'Creating…' : 'Create calendar'}</button>
            </form>
          )}
          {selectedCalendar && canEdit && (
            <form onSubmit={async (event) => {
              event.preventDefault();
              try {
                const index = Number(eraYear) * monthOptions.reduce((sum, item) => sum + item.days, 0);
                const era = await createEra.mutateAsync({ universeId, calendarId: activeCalendarId, data: { name: eraName.trim(), start_day_index: index } });
                setEraName('');
                setNotice(`Era “${era.name}” created.`);
                await refresh();
              } catch (error) { setNotice(message(error, 'Could not create this era.')); }
            }} className={`${panel} space-y-3`}>
              <h3 className="font-serif text-lg text-[#253a32]">Mark an era</h3>
              <input className={`${field} w-full`} required maxLength={100} value={eraName} onChange={(event) => setEraName(event.target.value)} placeholder="The Long Dawn" aria-label="Era name" />
              <label className="block text-[10px] text-[#788078]">Starting year<input className={`${field} mt-1 w-full`} type="number" value={eraYear} onChange={(event) => setEraYear(event.target.value)} aria-label="Era starting year" /></label>
              <button className={primary} type="submit" disabled={createEra.isPending}>{createEra.isPending ? 'Saving…' : 'Add era'}</button>
            </form>
          )}
          {selectedCalendar && canEdit && (
            <form onSubmit={(event) => void submitEvent(event)} className={`${panel} space-y-3`}>
              <h3 className="font-serif text-lg text-[#253a32]">Record an event</h3>
              <input className={`${field} w-full`} required maxLength={200} value={eventTitle} onChange={(event) => setEventTitle(event.target.value)} placeholder="Founding of the first city" aria-label="Event title" />
              <div className="grid grid-cols-3 gap-2">
                <input className={`${field} min-w-0`} aria-label="Year" type="number" value={year} onChange={(event) => setYear(event.target.value)} />
                <select className={`${field} min-w-0`} aria-label="Month" disabled={precision === 'year'} value={month} onChange={(event) => setMonth(event.target.value)}><option value="1">Month 1</option>{monthOptions.slice(1).map((item, index) => <option key={item.name} value={index + 2}>{item.name}</option>)}{monthOptions[0] && <option value="1">{monthOptions[0].name}</option>}</select>
                <input className={`${field} min-w-0`} aria-label="Day" type="number" min={1} max={monthOptions[Number(month) - 1]?.days ?? 1000} disabled={precision !== 'day'} value={day} onChange={(event) => setDay(event.target.value)} />
              </div>
              {(precision === 'range' || precision === 'approximate') && <input className={`${field} w-full`} aria-label="Event day" type="number" min={1} max={monthOptions[Number(month) - 1]?.days ?? 1000} value={day} onChange={(event) => setDay(event.target.value)} />}
              {precision === 'range' && <div className="grid grid-cols-3 gap-2"><input className={`${field} min-w-0`} aria-label="End year" type="number" value={endYear} onChange={(event) => setEndYear(event.target.value)} /><select className={`${field} min-w-0`} aria-label="End month" value={endMonth} onChange={(event) => setEndMonth(event.target.value)}>{monthOptions.map((item, index) => <option key={item.name} value={index + 1}>{item.name}</option>)}</select><input className={`${field} min-w-0`} aria-label="End day" type="number" min={1} max={monthOptions[Number(endMonth) - 1]?.days ?? 1000} value={endDay} onChange={(event) => setEndDay(event.target.value)} /></div>}
              {precision === 'approximate' && <label className="block text-[10px] text-[#788078]">Uncertainty before/after (days)<input className={`${field} mt-1 w-full`} type="number" min={0} max={10000000} value={uncertainty} onChange={(event) => setUncertainty(event.target.value)} /></label>}
              <select className={`${field} w-full`} value={precision} onChange={(event) => setPrecision(event.target.value as typeof precision)} aria-label="Date precision"><option value="day">Exact day</option><option value="month">Whole month</option><option value="year">Whole year</option><option value="range">Date range</option><option value="approximate">Approximate date</option></select>
              <button className={primary} type="submit" disabled={createEvent.isPending}>{createEvent.isPending ? 'Saving…' : 'Add event'}</button>
            </form>
          )}
          {selectedCalendar && <div className={panel}><p className="ww-kicker text-[#899087]">Calendar rules</p><p className="mt-2 text-xs leading-5 text-[#53655b]">{monthOptions.length} months · {monthOptions.reduce((total, item) => total + item.days, 0)} base days per year · {(config?.leap_rules ?? []).length} leap rules</p>{config?.leap_rules?.map((rule, index) => <p key={index} className="mt-2 text-[10px] text-[#788078]">+{rule.extra_days ?? 1} days in month {rule.month} every {rule.every_years} years</p>)}</div>}
        </aside>
      </div>
    </section>
  );
}

export default function AtlasChronos({ universeId, canEdit, initialView }: Props) {
  const [view, setView] = useState<'atlas' | 'chronos'>(initialView ?? 'atlas');
  return (
    <div className="space-y-6">
      <nav aria-label="Atlas and Chronos views" className="flex gap-2 border-b border-[#ded7ca] pb-3">
        <button type="button" className={`${view === 'atlas' ? primary : secondary}`} onClick={() => setView('atlas')}><MapPin size={14} /> Atlas</button>
        <button type="button" className={`${view === 'chronos' ? primary : secondary}`} onClick={() => setView('chronos')}><CalendarDays size={14} /> Chronos</button>
      </nav>
      {view === 'atlas' ? <AtlasPanel universeId={universeId} canEdit={canEdit} /> : <ChronosPanel universeId={universeId} canEdit={canEdit} />}
    </div>
  );
}
