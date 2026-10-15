// The stash in grams on a yarn card of the Inventory page: "4.3 balls · 215 g", Bought more, Correct and the
// history. Shows nothing while the switch is off. Fork-only (FORK.md).
// onCountChanged(itemId, quantity) tells the page the whole-ball count the server now has.
import { useEffect, useRef, useState } from 'react';
import { Plus, Scale, Clock } from 'lucide-react';
import { ft } from '../strings';
import { useStashStatus, useStashItem, ensureStashItems, refreshStashItems } from './stashStore';
import { amountText } from './stashNumbers';
import { AmountDialog, BallDetailsDialog } from './StashDialogs';
import StashHistory from './StashHistory';
import './Stash.css';

export default function StashCardExtras({ item, onCountChanged }) {
  const status = useStashStatus();
  if (!status?.enabled || item?.type !== 'yarn') return null;
  return <Extras item={item} onCountChanged={onCountChanged} />;
}

function Extras({ item, onCountChanged }) {
  const stash = useStashItem(item.id);
  const [dialog, setDialog] = useState(null);   // 'purchase' | 'correct' | 'details' | 'history'
  const lastQty = useRef(item.quantity);   // the count this card last knew about
  // An answer not to trust for the count: the one from before the count changed (or from before this card
  // appeared), while the server is asked again.
  const staleStash = useRef(stash);

  useEffect(() => { ensureStashItems(item.id); }, [item.id]);

  useEffect(() => {
    if (item.quantity !== lastQty.current) {
      // The +1/-1 buttons or an edit changed the count: ask the server for the grams again.
      lastQty.current = item.quantity;
      if (stash && stash.quantity !== item.quantity) { staleStash.current = stash; refreshStashItems(); }
      return;
    }
    if (!stash || stash === staleStash.current) return;
    staleStash.current = null;
    // The server keeps the whole-ball count in step with the grams: let the page show the same.
    if (stash.quantity != null && stash.quantity !== item.quantity) {
      lastQty.current = stash.quantity;
      onCountChanged?.(item.id, stash.quantity);
    }
  }, [stash, item.id, item.quantity, onCountChanged]);

  if (!stash) return null;
  const grams = stash.mode === 'grams';
  const close = () => setDialog(null);

  return (
    <div className="st-card-extras">
      <p className="st-card-amount">{grams ? amountText(stash.balls, stash.grams) : amountText(stash.quantity, null)}</p>
      {!grams && stash.yarn_id && (
        <button type="button" className="st-link" onClick={() => setDialog('details')}>{ft('addBallWeight')}</button>
      )}
      <div className="st-card-buttons">
        <button type="button" className="st-btn st-btn--small st-btn--primary" onClick={() => setDialog('purchase')}>
          <Plus size={18} aria-hidden="true" /> {ft('boughtMore')}
        </button>
        <button type="button" className="st-btn st-btn--small st-btn--secondary" onClick={() => setDialog('correct')}>
          <Scale size={18} aria-hidden="true" /> {ft('correct')}
        </button>
      </div>
      {grams && (
        <button type="button" className="st-link st-link--quiet" onClick={() => setDialog('history')}>
          <Clock size={16} aria-hidden="true" /> {ft('gramHistory')}
        </button>
      )}

      {(dialog === 'purchase' || dialog === 'correct') && (
        <AmountDialog kind={dialog} item={stash} onClose={close} />
      )}
      {dialog === 'details' && (
        <BallDetailsDialog yarnId={stash.yarn_id} yarnName={stash.yarn_name || stash.name} onClose={close} />
      )}
      {dialog === 'history' && <StashHistory item={stash} onClose={close} />}
    </div>
  );
}
