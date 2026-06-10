// Firebase Admin bootstrap — handler modules import from here so
// initializeApp runs exactly once regardless of import order.
import { initializeApp } from 'firebase-admin/app';
import { getFirestore } from 'firebase-admin/firestore';

initializeApp();

export const db = getFirestore();
