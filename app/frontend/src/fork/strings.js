// English text for the fork's own screens (see FORK.md). Plain British English for a knitter.
// ft('key', { name: 'value' }) fills in {name} placeholders.

const STRINGS = {
  // Tab
  guidedTab: 'Guided',

  // Admin settings (Settings, Knitting upgrades)
  settingsNav: 'Knitting upgrades',
  settingsNavSub: 'Guided versions and the stash in grams',
  settingsTitle: 'Knitting upgrades',
  settingsIntro: 'Extra features for this library. Each one can be switched off again, and nothing that was saved is lost.',
  settingsEnable: 'Guided versions',
  settingsEnableSub: 'Adds a Guided tab to every pattern. A guided version splits a pattern into steps and shows only the chosen size\'s numbers. It is made by the AI service set up under AI.',
  settingsStash: 'Stash in grams',
  settingsStashSub: 'Counts yarn in grams as well as balls, reads ball bands with the camera, and keeps a history of every change to the stash.',
  settingsNeedsAI: 'The AI connection is not set up yet. Guided versions and reading ball bands need it: add the address and key under AI first.',
  settingsModel: 'Model',
  settingsModelSub: 'The AI model that makes guided versions and reads ball bands, as named by the AI service.',
  settingsSave: 'Save',
  settingsSaved: 'Saved.',
  loading: 'Loading…',

  // Empty state
  introTitle: 'A guided version of this pattern',
  introText: 'A guided version splits the pattern into steps and shows only your size\'s numbers. It takes about a minute. You can lock your iPad while it works.',
  makeGuided: 'Make a guided version',
  starting: 'Starting…',
  notSetUp: 'The AI connection is not set up yet.',
  notSetUpAdmin: 'You can set it up in Settings, under AI.',
  notSetUpUser: 'Ask the person who looks after this app to set it up in Settings, under AI.',
  switchedOff: 'Guided versions are switched off.',
  loadingGuide: 'Opening the guided version…',
  loadFailed: 'We could not reach the app just now. Trying again…',

  // Building
  buildingTitle: 'Making your guided version',
  buildingHint: 'You can lock your iPad or leave this page. It keeps going, and this page catches up when you come back.',
  waitingToStart: 'Waiting to start',
  percentDone: '{percent}% done',
  timeSoFar: 'Time so far: {time}',
  minSec: '{m} min {s} sec',
  secOnly: '{s} sec',
  stageDone: 'Done',
  stageNow: 'Working on this now',
  stageWaiting: 'Still to come',
  stageSkipped: 'Not needed',
  stage_read: 'Reading the pattern',
  stage_pictures: 'Reading pages that are pictures',
  stage_outline: 'Finding sizes, yarn and sections',
  stage_sections: 'Writing the steps',
  stage_checks: 'Checking every number against the pattern',
  takingLonger: 'This part is taking a little longer than usual. It is still working.',
  stop: 'Stop',
  stopConfirm: 'Stop making the guided version? You can start again later.',
  stopYes: 'Yes, stop',
  stopNo: 'No, keep going',
  stopping: 'Stopping…',
  updatedJustNow: 'Updated just now',
  updatedSecondsAgo: 'Updated {n} seconds ago',
  updatedMinutesAgo: 'Updated {n} min ago',
  checking: 'Checking…',
  reconnecting: 'Reconnecting…',
  reconnectingHint: 'Lost touch with the app for a moment. Still trying; nothing is lost.',

  // Finished
  readyBanner: 'Your guided version is ready.',
  failedTitle: 'The guided version could not be made this time',
  failedDefault: 'Something went wrong while reading the pattern.',
  cancelledTitle: 'You stopped making the guided version',
  cancelledText: 'Nothing was changed.',
  keptEarlier: 'Your earlier guided version is still below.',
  tryAgain: 'Try again',
  hideNotice: 'Hide this message',

  // Guide header
  versionMade: 'Version {version}, made {date}',
  byDesigner: 'by {designer}',
  notCheckedYet: 'Made by the computer from the pattern. Keep the pattern to hand and compare as you knit.',
  makeAgain: 'Make it again',
  makeAgainConfirm: 'Make a new guided version? It replaces this one.',
  makeAgainYes: 'Yes, make it again',
  cancel: 'Cancel',

  // Size and choices
  yourSize: 'Your size',
  chooseSize: 'Choose your size to see only your numbers.',
  chooseChoice: 'Choose your {name}.',
  sizeChosen: 'Showing the numbers for size {size}.',

  // Things to check
  thingsToCheck: 'Things to check',
  thingsToCheckHint: 'The pattern may be unclear or have a mistake in these places.',
  showAll: 'Show all {n}',
  showFewer: 'Show fewer',

  // Materials
  materials: 'What you need',
  yarn: 'Yarn',
  needles: 'Needles',
  gauge: 'Tension',
  otherThings: 'Also',
  amountForSize: '{amount} for your size',
  length: 'length {length}',

  // Sections and steps
  stepsCount: '{n} steps',
  oneStep: '1 step',
  workedTimes: 'Worked {n} times: {labels}',
  mirrored: 'The second one is worked as a mirror image.',
  showSteps: 'Show steps',
  hideSteps: 'Hide steps',
  openAll: 'Open all sections',
  closeAll: 'Close all sections',
  notForSize: 'Not for this size',
  otherHidden: '{n} steps are not for {choice}, so they are hidden.',
  otherHiddenOne: '1 step is not for {choice}, so it is hidden.',
  otherShown: 'Steps that are not for {choice} are shown greyed out.',
  showOther: 'Show them',
  hideOther: 'Hide them',
  notForChoice: 'Not for {choice}',
  optional: 'Optional',
  checkPage: 'Check against the pattern, page {page}',
  checkPattern: 'Check against the pattern',
  fromPicture: 'Read from a picture in the pattern',
  fromPicturePage: 'Read from a picture in the pattern, page {page}',
  repeatLabel: 'Repeat',
  targetLabel: 'Work',
  checkLabel: 'Check',
  atSameTime: 'At the same time',
  allSizes: 'All sizes',
  close: 'Close',
  notGiven: 'not given',
  notThisSize: 'not this size',
  tapNumber: 'Tap a number to see it for every size.',

  // Targets, repeats, checkpoints
  untilLength: 'until it measures {length}',
  fromWhere: '{from}',
  untilRow: 'until row {row}',
  times: '{n} times',
  checkStitches: 'You should now have {n} stitches',
  checkRows: 'You should have worked {n} rows',
  everyN: 'every {n}',
  timesN: '{n} times in all',

  // ---------------------------------------------------------------- the stash in grams
  // Ball details
  ballDetails: 'Ball details',
  ballDetailsHint: 'From the ball band. With the grams per ball, the stash is counted in grams as well as balls.',
  gramsPerBall: 'Grams per ball',
  metresPerBall: 'Metres per ball',
  yarnWeight: 'Weight',
  yarnWeightPlaceholder: 'For example DK or Aran',
  fibre: 'Fibre',
  fibrePlaceholder: 'For example 100% wool',
  needleSize: 'Needle size',
  needleFrom: 'From (mm)',
  needleTo: 'To (mm)',
  tension: 'Tension over 10 cm',
  tensionLabel: 'Tension',
  stitches: 'Stitches',
  rows: 'Rows',
  care: 'Care',
  carePlaceholder: 'For example hand wash, lay flat to dry',
  onTheBand: 'On the band: {text}',
  pleaseCheck: 'Please check',
  noBallDetails: 'No ball details yet.',
  addBallDetails: 'Add ball details',
  editBallDetails: 'Edit',
  needleRange: '{from} to {to} mm',
  needleOne: '{mm} mm',
  tensionText: '{stitches} stitches and {rows} rows over 10 cm',
  tensionStitches: '{stitches} stitches over 10 cm',
  tensionRows: '{rows} rows over 10 cm',
  gramsValue: '{n} g',
  metresValue: '{n} m',
  notANumber: '{label} should be a number, like 50 or 4,5.',
  specNotSaved: 'The yarn was saved, but its ball details were not: {message}',
  colourNotSaved: 'The yarn was saved, but its colour could not be added. You can add it on the yarn\'s page.',

  // Ball band photo
  photographBand: 'Photograph the ball band',
  photographBandSub: 'The details are read from the photo and filled in for you to check.',
  choosePhoto: 'Choose a photo instead',
  takeAnother: 'Take another photo',
  readingBand: 'Reading the ball band…',
  readingBandHint: 'This can take up to a minute.',
  bandRead: 'Done. Check the details below, then save.',
  bandReadChecks: 'Done. The details marked “Please check” were hard to read. Check them, then save.',
  bandNothing: 'Nothing could be read from this photo. Try again closer to the band, in good light.',
  bandFailed: 'The ball band could not be read just now. Try again, or fill in the form yourself.',
  bandNotAvailable: 'Reading ball bands needs the AI connection, which is not set up yet.',
  bandPhotoAlt: 'The ball band photo',
  bandColour: 'Colour on the band: {colour}',
  bandDyeLot: 'Dye lot: {lot}',
  addColourToo: 'Also add this colour to the yarn',
  usePhotoAsPicture: 'Use this photo as the yarn\'s picture',

  // Stash on the inventory cards
  ballsAndGrams: '{balls} balls · {grams} g',
  oneBallAndGrams: '{balls} ball · {grams} g',
  ballsOnly: '{balls} balls',
  oneBall: '1 ball',
  addBallWeight: 'Add the ball weight to count in grams',
  boughtMore: 'Bought more',
  correct: 'Correct',
  gramHistory: 'History in grams',

  // Dialogs
  save: 'Save',
  saving: 'Saving…',
  balls: 'Balls',
  unitChoice: 'Balls or grams',
  grams: 'Grams',
  howMany: 'How many did you buy?',
  howMuchNow: 'How much do you have now?',
  howMuchNowHint: 'Count the balls, or weigh what you have and give the grams.',
  ballsUnit: 'balls',
  gramsUnit: 'g',
  note: 'Note (optional)',
  notePurchase: 'For example where you bought it',
  noteCorrect: 'For example weighed on the kitchen scales',
  stashNow: 'The stash has {amount} now.',
  stashAfter: 'Afterwards: {amount}.',
  wholeBallsOnly: 'This yarn is counted in whole balls until it has a ball weight.',
  giveAmount: 'Give a number first.',
  couldNotSave: 'This could not be saved just now. Check the connection and try again.',
  couldNotLoad: 'This could not be loaded just now. Check the connection and try again.',
  tryAgainShort: 'Try again',

  // History
  historyEmpty: 'No changes yet.',
  historyThen: 'Then {amount}',
  historyBy: 'by {name}',
  reason_opening: 'Starting amount',
  reason_purchase: 'Bought',
  reason_correction: 'Corrected',
  reason_ball_count: 'Ball count changed',
  reason_project_reserve: 'Set aside for a project',
  reason_project_release: 'No longer set aside',
  reason_project_use: 'Used in a project',
  reason_leftover: 'Left over from a project',
  reason_other: 'Changed',
};

export function ft(key, vars) {
  let text = STRINGS[key];
  if (text == null) return key;
  if (vars) {
    text = text.replace(/\{(\w+)\}/g, (match, name) => (vars[name] != null ? String(vars[name]) : match));
  }
  return text;
}

/** Like ft, but a placeholder may be a React element: returns a list of strings and elements to render. */
export function ftParts(key, vars) {
  const text = STRINGS[key] ?? key;
  return text.split(/(\{\w+\})/).filter(Boolean).map((part) => {
    const m = part.match(/^\{(\w+)\}$/);
    return m && vars && vars[m[1]] != null ? vars[m[1]] : part;
  });
}

export default STRINGS;
