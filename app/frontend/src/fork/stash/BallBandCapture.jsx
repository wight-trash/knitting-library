// "Photograph the ball band" in the Add / edit yarn form. On a phone or tablet it opens the camera; on a computer
// it opens a file chooser. The photo stays in view beside the form while the knitter checks it. Fork-only (FORK.md).
import { useRef } from 'react';
import { Camera, ImageIcon, Loader } from 'lucide-react';
import { ft } from '../strings';
import { CheckBadge } from './BallDetailsFields';
import './Stash.css';

export default function BallBandCapture({ available, band, readPhoto, addColour, setAddColour, usePicture, choosePicture }) {
  const cameraRef = useRef(null);
  const libraryRef = useRef(null);
  const reading = band.state === 'reading';

  const onFile = (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';           // the same photo can be chosen again
    if (file) readPhoto(file);
  };

  const inputs = (
    <>
      <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="st-hidden-input"
        onChange={onFile} data-testid="ballband-camera" tabIndex={-1} aria-hidden="true" />
      <input ref={libraryRef} type="file" accept="image/*" className="st-hidden-input"
        onChange={onFile} data-testid="ballband-library" tabIndex={-1} aria-hidden="true" />
    </>
  );

  if (!available) {
    return <p className="st-hint st-band-off">{ft('bandNotAvailable')}</p>;
  }

  if (!band.photo) {
    return (
      <div className="st-band">
        {inputs}
        <button type="button" className="st-band-btn" onClick={() => cameraRef.current?.click()}>
          <Camera size={28} aria-hidden="true" />
          <span className="st-band-btn-text">
            <span className="st-band-btn-title">{ft('photographBand')}</span>
            <span className="st-band-btn-sub">{ft('photographBandSub')}</span>
          </span>
        </button>
        <button type="button" className="st-link" onClick={() => libraryRef.current?.click()}>
          <ImageIcon size={18} aria-hidden="true" /> {ft('choosePhoto')}
        </button>
      </div>
    );
  }

  return (
    <div className="st-band st-band--photo">
      {inputs}
      <div className="st-band-photo-wrap">
        <img src={band.photo} alt={ft('bandPhotoAlt')} className="st-band-photo" />
        {reading && (
          <div className="st-band-reading" role="status">
            <Loader size={26} className="st-spin" aria-hidden="true" />
            <span>{ft('readingBand')}</span>
          </div>
        )}
      </div>
      <div className="st-band-info">
        {reading && <p className="st-hint">{ft('readingBandHint')}</p>}
        {band.state === 'done' && (
          <p className="st-text st-band-ok" role="status">
            {band.hasChecks ? <>{ft('bandReadChecks')} <CheckBadge /></> : ft('bandRead')}
          </p>
        )}
        {band.state === 'empty' && <p className="st-error" role="alert">{ft('bandNothing')}</p>}
        {band.state === 'error' && <p className="st-error" role="alert">{band.message}</p>}
        {band.state === 'done' && band.colour && (
          <label className="st-check-row">
            <input type="checkbox" checked={addColour} onChange={(e) => setAddColour(e.target.checked)} />
            <span>{ft('bandColour', { colour: band.colour })}. {ft('addColourToo')}</span>
          </label>
        )}
        {band.state === 'done' && band.dyeLot && <p className="st-hint">{ft('bandDyeLot', { lot: band.dyeLot })}</p>}
        {!reading && band.small && (
          <label className="st-check-row">
            <input type="checkbox" checked={usePicture} onChange={(e) => choosePicture(e.target.checked)} />
            <span>{ft('usePhotoAsPicture')}</span>
          </label>
        )}
        {!reading && (
          <div className="st-band-again">
            <button type="button" className="st-btn st-btn--small st-btn--secondary" onClick={() => cameraRef.current?.click()}>
              <Camera size={18} aria-hidden="true" /> {ft('takeAnother')}
            </button>
            <button type="button" className="st-link" onClick={() => libraryRef.current?.click()}>
              <ImageIcon size={18} aria-hidden="true" /> {ft('choosePhoto')}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
