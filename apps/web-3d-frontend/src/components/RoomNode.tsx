import React, { useMemo, useRef } from 'react';
import { Html } from '@react-three/drei';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { OcupacaoSala, Sala } from '../lib/types';
import { INSTED, corPorTaxa } from '../lib/theme';

interface RoomNodeProps {
  sala: Sala;
  offsetY: number;
  ocupacao?: OcupacaoSala | null;
  destacada: boolean;
  piscandoEm?: number;
  mostrarRotulo: boolean;
  onSelecionar: (salaId: string) => void;
}

/**
 * Uma sala da maquete: laje, contorno das paredes e (opcionalmente) rotulo
 * flutuante com a aula em andamento. A cor do piso segue a taxa de presenca,
 * o que permite ler o campus inteiro de relance.
 */
export const RoomNode: React.FC<RoomNodeProps> = ({
  sala,
  offsetY,
  ocupacao,
  destacada,
  piscandoEm,
  mostrarRotulo,
  onSelecionar,
}) => {
  const lajeRef = useRef<THREE.Mesh>(null!);
  const { largura, profundidade, altura } = sala.dimensao;

  const centro = useMemo<[number, number, number]>(
    () => [
      sala.posicao.x + largura / 2,
      sala.posicao.y + offsetY,
      sala.posicao.z + profundidade / 2,
    ],
    [sala, largura, profundidade, offsetY],
  );

  const emAula = !!ocupacao?.em_aula;
  const presentes = (ocupacao?.presentes ?? 0) + (ocupacao?.atrasados ?? 0);
  const taxa = ocupacao?.esperados
    ? (100 * presentes) / ocupacao.esperados
    : 0;

  const corPiso = emAula ? corPorTaxa(taxa) : '#232a35';
  const corBorda = destacada ? INSTED.primary : emAula ? corPorTaxa(taxa) : INSTED.border;

  // Contorno das paredes (wireframe leve, sem oclusao visual).
  const arestas = useMemo(
    () => new THREE.EdgesGeometry(new THREE.BoxGeometry(largura, altura, profundidade)),
    [largura, altura, profundidade],
  );

  // Pulso curto quando a sala recebe uma passagem de catraca.
  useFrame(({ clock }) => {
    if (!lajeRef.current) return;
    const material = lajeRef.current.material as THREE.MeshStandardMaterial;
    if (!piscandoEm) {
      material.emissiveIntensity = destacada ? 0.55 : emAula ? 0.18 : 0.04;
      return;
    }
    const decorrido = (Date.now() - piscandoEm) / 1000;
    if (decorrido > 1.4) {
      material.emissiveIntensity = destacada ? 0.55 : emAula ? 0.18 : 0.04;
      return;
    }
    const pulso = Math.max(0, 1 - decorrido / 1.4);
    material.emissiveIntensity =
      (emAula ? 0.18 : 0.04) + pulso * (0.6 + 0.2 * Math.sin(clock.elapsedTime * 14));
  });

  return (
    <group
      position={centro}
      onClick={(e) => {
        e.stopPropagation();
        onSelecionar(sala.id);
      }}
      onPointerOver={(e) => {
        e.stopPropagation();
        document.body.style.cursor = 'pointer';
      }}
      onPointerOut={() => {
        document.body.style.cursor = 'auto';
      }}
    >
      {/* Laje / piso da sala */}
      <mesh ref={lajeRef} position={[0, 0.02, 0]} receiveShadow>
        <boxGeometry args={[largura, 0.12, profundidade]} />
        <meshStandardMaterial
          color={corPiso}
          emissive={corPiso}
          emissiveIntensity={emAula ? 0.18 : 0.04}
          roughness={0.85}
          metalness={0.05}
          transparent
          opacity={emAula ? 0.94 : 0.62}
        />
      </mesh>

      {/* Contorno das paredes */}
      <lineSegments position={[0, altura / 2, 0]}>
        <primitive object={arestas} attach="geometry" />
        <lineBasicMaterial
          color={corBorda}
          transparent
          opacity={destacada ? 0.95 : emAula ? 0.5 : 0.24}
        />
      </lineSegments>

      {mostrarRotulo && (
        <Html
          position={[0, altura * 0.72, 0]}
          center
          distanceFactor={30}
          zIndexRange={[10, 0]}
          style={{ pointerEvents: 'none' }}
        >
          <div className={`room-tag ${emAula ? 'ativa' : ''} ${destacada ? 'foco' : ''}`}>
            <strong>{sala.nome}</strong>
            {emAula ? (
              <span>
                {presentes}/{ocupacao?.esperados} · {taxa.toFixed(0)}%
              </span>
            ) : (
              <span className="muted">
                {sala.capacidade ? `${sala.capacidade} lugares · livre` : 'sem carteiras'}
              </span>
            )}
          </div>
        </Html>
      )}
    </group>
  );
};
