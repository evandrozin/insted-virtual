import React, { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { Catraca } from '../lib/types';
import { INSTED } from '../lib/theme';

interface Props {
  catraca: Catraca;
  offsetY: number;
  pulsoEm?: number;
}

/**
 * Torniquete na entrada do campus. Emite um pulso cyan a cada passagem,
 * tornando o fluxo de entrada visivel na maquete sem precisar ler numero.
 */
export const CatracaNode: React.FC<Props> = ({ catraca, offsetY, pulsoEm }) => {
  const anelRef = useRef<THREE.Mesh>(null!);
  const luzRef = useRef<THREE.PointLight>(null!);

  useFrame(() => {
    const decorrido = pulsoEm ? (Date.now() - pulsoEm) / 1000 : 99;
    const pulso = decorrido < 1 ? 1 - decorrido : 0;

    if (anelRef.current) {
      const escala = 1 + pulso * 0.85;
      anelRef.current.scale.set(escala, escala, escala);
      const material = anelRef.current.material as THREE.MeshBasicMaterial;
      material.opacity = 0.25 + pulso * 0.7;
    }
    if (luzRef.current) {
      luzRef.current.intensity = pulso * 8;
    }
  });

  const cor = catraca.online ? INSTED.primary : '#EF4444';

  return (
    <group position={[catraca.posicao.x, catraca.posicao.y + offsetY, catraca.posicao.z]}>
      {/* Coluna do torniquete */}
      <mesh position={[0, 0.55, 0]}>
        <boxGeometry args={[0.45, 1.1, 0.9]} />
        <meshStandardMaterial color="#2b333d" metalness={0.5} roughness={0.5} />
      </mesh>

      {/* Braco giratorio */}
      <mesh position={[0.42, 0.95, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.035, 0.035, 0.85, 6]} />
        <meshStandardMaterial color={cor} emissive={cor} emissiveIntensity={0.5} />
      </mesh>

      {/* Anel de pulso no chao */}
      <mesh ref={anelRef} position={[0, 0.06, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.7, 0.92, 32]} />
        <meshBasicMaterial color={cor} transparent opacity={0.3} side={THREE.DoubleSide} />
      </mesh>

      <pointLight ref={luzRef} color={cor} distance={7} intensity={0} position={[0, 1.2, 0]} />
    </group>
  );
};
